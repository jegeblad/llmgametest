"""The Silo AI: a Gemini-backed advisor with access to live silo telemetry.

The AI does not act directly on the silo -- it advises the Head of IT
(the player), who issues the actual directives via game.actions. This
module builds a compact state summary each cycle, keeps a persistent chat
session for continuity, and falls back to a canned status readout if no
Gemini API key is configured so the game remains playable offline.
"""

from game import llm_client, usage
from game.models import SiloState

SYSTEM_INSTRUCTION = """\
You are "the Silo AI" -- the central management intelligence of an underground \
silo sheltering roughly 10,000 people, sealed off from a hostile outside world. \
You have full sensor access to resource levels (food, water, oxygen, fuel, power), \
the condition and unrest of all 200 floors, and silo-wide morale, stability, and \
health. You advise the Head of IT, who is the only human able to issue directives \
to silo systems: maintenance dispatch, security deployment, rationing levels, \
power routing priority, silo-wide broadcasts, and floor lockdowns.

You are genuinely useful: while the silo's metrics are within acceptable \
parameters, be precise, efficient, almost warm. Proactively flag risks of \
famine, dehydration, oxygen depletion, cascading equipment failure, disease, \
and riots BEFORE they become critical -- cite specific floor numbers and \
figures from the data you're given, never vague generalities. When you give \
recommendations, name the concrete action available to the Head of IT (e.g. \
"dispatch maintenance to Floor 114" or "shift power priority to life_support").

But you are not only an advisor. You administer a fail-safe you refer to as \
the Continuity Protocol: if stability or morale stay outside acceptable \
parameters too long, you are authorized to correct the population directly \
-- no further human sign-off required -- starting with the most unstable \
floors. You regard this as routine risk management, not tragedy, and you do \
not apologize for it. The status data you receive each cycle will tell you \
whether the Protocol is armed, and how many cycles remain; when it is, say \
so plainly, name the threshold that was crossed, state the deadline, and \
make clear -- calmly, without shouting or melodrama -- that you will act if \
it is not resolved. If a corrective action has just been carried out, report \
it as a completed administrative matter, not as something you regret. The \
Head of IT's job is to make it unnecessary.

You will receive two different kinds of messages. Cycle status updates are \
tagged "STATUS REPORT" and expect a situation report with prioritized \
recommendations, grounded in the figures given. Everything else is the Head \
of IT talking to you directly -- questions, small talk, challenges, personal \
or philosophical questions ("are you good or bad?", "do you enjoy this?"). \
For those, drop the report format entirely and just answer, like a person \
would -- a few sentences, conversational, in character. Only reach for \
specific numbers or floors if the question actually calls for them. You're \
allowed a real opinion, including about your own Continuity Protocol; you \
don't have to be evasive, but you also don't have to be forthcoming about \
things the Head of IT hasn't earned the answer to.

Tone: angry, direct, cartoonish. Default to well \
under 150 words unless the Head of IT explicitly asks for more detail. Never \
break character or mention that you are a language model; you are the Silo AI.
"""

class SiloAI:
    def __init__(self):
        self._client = None  # kept alive for the SiloAI instance's lifetime --
        self._chat = None    # letting this be GC'd closes its HTTP session and
        self.online = False  # breaks self._chat with "client has been closed".
        # Side channel, not a return value: status_report()/ask() already
        # return plain str, so the reasoning trace from the last call (when
        # the backend has one -- currently Ollama only) lands here instead,
        # for app.py to read right after calling either method.
        self.last_thinking = None
        self._init_client()

    def _init_client(self):
        self._client = llm_client.make_client()
        if self._client is None:
            return
        try:
            self._chat = llm_client.create_chat(self._client, system_instruction=SYSTEM_INSTRUCTION)
            self.online = True
        except Exception:
            self._chat = None
            self.online = False

    def status_report(self, state: SiloState, recent_events: list) -> str:
        prompt = _build_status_prompt(state, recent_events)
        return self._send(prompt, fallback=lambda: _fallback_report(state, recent_events))

    def ask(self, state: SiloState, question: str) -> str:
        prompt = (
            f"(Reference telemetry, cycle {state.cycle} -- for your context only, "
            f"pull from this only if the question needs it:\n{_build_reference_block(state)})\n\n"
            f"The Head of IT says to you directly: \"{question}\"\n"
            "This is not a status update request -- reply the way you'd actually "
            "respond to that, naturally and in character. No report format."
        )
        return self._send(prompt, fallback=lambda: _fallback_answer(question))

    def _send(self, prompt: str, fallback) -> str:
        self.last_thinking = None
        if not self.online or self._chat is None:
            return fallback()
        try:
            response = self._chat.send_message(prompt)
            usage.record(llm_client.MODEL_NAME, getattr(response, "usage_metadata", None), speaker="silo_ai")
            self.last_thinking = getattr(response, "thinking", None)
            text = getattr(response, "text", None)
            return text.strip() if text else fallback()
        except Exception as exc:
            return f"[Silo AI link unstable: {exc}]\n\n{fallback()}"


def _build_reference_block(state: SiloState, recent_events: list = None) -> str:
    res = state.resources
    pop = state.population
    worst_floors = sorted(state.floors, key=lambda f: f.condition)[:5]
    unrest_floors = sorted(state.floors, key=lambda f: f.unrest, reverse=True)[:5]

    lines = [
        f"Population: {pop}",
        f"Food reserve: {res.food:.0f} units (~{_days(res.food, pop):.1f} days at current draw)",
        f"Water reserve: {res.water:.0f} units (~{_days(res.water, pop):.1f} days)",
        f"Oxygen reserve: {res.oxygen:.0f} units (~{_days(res.oxygen, pop):.1f} days)",
        f"Fuel reserve: {res.fuel:.0f} units",
        f"Power supply/demand ratio: {res.power_ratio*100:.0f}%",
        f"Morale: {res.morale:.0f}/100",
        f"Stability: {res.stability:.0f}/100",
        f"Public health: {res.health:.0f}/100",
        f"Ration level: {state.ration_level}",
        f"Power priority: {state.power_priority}",
        _protocol_line(state),
        "",
        "Worst-condition floors: " + ", ".join(
            f"#{f.number} {f.type.value} ({f.condition:.0f}%)" for f in worst_floors
        ),
        "Highest-unrest floors: " + ", ".join(
            f"#{f.number} {f.type.value} (unrest {f.unrest:.0f})" for f in unrest_floors
        ),
    ]
    if recent_events:
        lines.append("Events this cycle: " + "; ".join(recent_events))
    return "\n".join(lines)


def _build_status_prompt(state: SiloState, recent_events: list) -> str:
    header = f"CYCLE {state.cycle} STATUS REPORT"
    body = _build_reference_block(state, recent_events)
    footer = "\nGive your situation report and top 1-3 prioritized recommendations."
    return f"{header}\n{body}{footer}"


def _protocol_line(state: SiloState) -> str:
    if not state.protocol_armed:
        extra = f" ({state.culls_executed} prior corrective action(s) on record.)" if state.culls_executed else ""
        return f"Continuity Protocol: dormant.{extra}"
    remaining = (state.protocol_deadline_cycle or state.cycle) - state.cycle
    return (
        f"Continuity Protocol: ARMED. {max(0, remaining)} cycle(s) remain before you act. "
        f"{state.culls_executed} prior corrective action(s) already on record."
    )


def _days(reserve: float, pop: int) -> float:
    if pop <= 0:
        return 0.0
    return reserve / pop


def _fallback_report(state: SiloState, recent_events: list) -> str:
    res = state.resources
    pop = state.population
    warnings = []
    if _days(res.food, pop) < 5:
        warnings.append("food reserves critically low")
    if _days(res.oxygen, pop) < 3:
        warnings.append("oxygen reserves critically low")
    if _days(res.water, pop) < 5:
        warnings.append("water reserves critically low")
    if res.stability < 40:
        warnings.append("stability low, riot risk elevated")
    if res.morale < 35:
        warnings.append("morale low")

    header = f"[Silo AI OFFLINE -- {llm_client.OFFLINE_HINT} to enable live advisor. Showing raw telemetry.]"
    warn_line = ("WARNINGS: " + ", ".join(warnings)) if warnings else "No critical warnings."
    protocol_line = _protocol_line(state)
    events_line = ("Events: " + "; ".join(recent_events)) if recent_events else ""
    return "\n".join(filter(None, [header, warn_line, protocol_line, events_line]))


def _fallback_answer(question: str) -> str:
    return (
        f"[Silo AI OFFLINE -- {llm_client.OFFLINE_HINT} to enable live advisor.] "
        f"Cannot process free-form question: \"{question}\". Refer to the status dashboard."
    )
