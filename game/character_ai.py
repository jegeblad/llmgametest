"""Chat sessions for the five named characters.

Distinct from the Silo AI on purpose: each character is a real person with
their own personality and a domain scoped to their own patrol floors -- they
do not have silo-wide sensor access, only what they'd plausibly know from
their own rounds and staff. Their current mood (see game/characters.py)
colors their tone each time they're asked something.

Sessions are created lazily per character on first contact, not all five up
front, so a player who only ever talks to the Silo AI doesn't pay for five
extra chat sessions they never use.

Responses are structured, not just free text: alongside what they say, the
model also reports a physical reaction (eyebrows, eyes, mouth, shoulders,
arms, body lean, legs) via Gemini's schema-constrained JSON output, so the
UI has something to actually animate/react to instead of only words. This
was validated live before relying on it: with an explicit instruction to
vary pose with the emotional content rather than default to a neutral
stance, good news produced raised eyebrows + big smile + a wide gesture,
bad news produced a frown + slumped shoulders + a shrug, and a sudden alarm
produced a lean/step and both arms up -- genuinely differentiated, not a
static default repeated every turn.
"""

import json
from dataclasses import dataclass

from game import llm_client, usage

_MOOD_TONE_HINTS = {
    "happy": "You're in a genuinely good mood today -- let some warmth or humor show.",
    "grumpy": "You're grumpy today -- short-tempered and a bit short with people, but not cruel.",
    "concerned": "You're worried about something in your area -- let a bit of unease color your answers.",
    "frustrated": "You're frustrated -- things in your area are going badly and it shows.",
    "tired": "You're exhausted -- answers can be terser or more resigned than usual.",
    "hungry": "You're hungry, like everyone on cut rations -- it's hard to think about much else.",
}

# --- structured reaction: schema, dataclass, human-readable rendering -------

EYEBROW_VALUES = ["static", "raise_both", "raise_left", "raise_right"]
EYE_VALUES = ["look_up", "look_down", "look_left", "look_right", "look_straight"]
MOUTH_VALUES = ["straight", "open", "smile", "frown", "big_smile", "raise_one_side"]
SHOULDER_VALUES = ["raise", "lower", "normal"]
# "at_sides" is the genuine neutral/relaxed option -- every other field has
# one (static, look_straight, straight, normal, straight, stand) but the
# original arm enum didn't, so for calm/routine dialogue the model (and our
# own fallback default) kept reaching for "shrug" as the closest thing to
# neutral, making everyone look perpetually uncertain. Confirmed as the
# actual cause by checking prior live transcripts, not just guessed at.
ARM_VALUES = ["at_sides", "raise_both", "raise_left", "raise_right", "shrug", "wide_gesture", "italian_hand_gesture"]
BODY_VALUES = ["straight", "lean_left", "lean_right"]
LEG_VALUES = ["stand", "step_left", "step_right", "walk", "jump"]


@dataclass
class CharacterReaction:
    text: str
    eyebrow_reaction: str = "static"
    eye_movement: str = "look_straight"
    mouth_movement: str = "straight"
    shoulder_movement: str = "normal"
    arm_movement: str = "at_sides"
    body: str = "straight"
    legs: str = "stand"
    # Not part of the JSON schema the model fills -- attached separately in
    # ask() from the response's own thinking field, when the backend has one
    # (currently only game/ollama_client.py; Gemini responses have none).
    thinking: str = None


def _enum_schema(values):
    return {"type": "string", "enum": values}


def _build_reaction_schema() -> dict:
    """Plain JSON Schema dict -- backend-agnostic. game/gemini_client.py
    converts this to a google.genai types.Schema itself when that backend
    is live; game/ollama_client.py passes it straight through as-is."""
    return {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "What the character says aloud."},
            "eyebrow_reaction": _enum_schema(EYEBROW_VALUES),
            "eye_movement": _enum_schema(EYE_VALUES),
            "mouth_movement": _enum_schema(MOUTH_VALUES),
            "shoulder_movement": _enum_schema(SHOULDER_VALUES),
            "arm_movement": _enum_schema(ARM_VALUES),
            "body": _enum_schema(BODY_VALUES),
            "legs": _enum_schema(LEG_VALUES),
        },
        "required": ["text", "eyebrow_reaction", "eye_movement", "mouth_movement",
                      "shoulder_movement", "arm_movement", "body", "legs"],
    }


# Phrases for the stage-direction caption. A value mapped to None is the
# "neutral" pose for that field and gets omitted so the caption only calls
# out what's actually expressive.
_POSE_PHRASES = {
    "eyebrow_reaction": {
        "static": None, "raise_both": "eyebrows raised",
        "raise_left": "left eyebrow raised", "raise_right": "right eyebrow raised",
    },
    "eye_movement": {
        "look_straight": None, "look_up": "eyes up", "look_down": "eyes down",
        "look_left": "eyes left", "look_right": "eyes right",
    },
    "mouth_movement": {
        "straight": None, "open": "mouth open", "smile": "smiling",
        "frown": "frowning", "big_smile": "big smile", "raise_one_side": "smirking",
    },
    "shoulder_movement": {
        "normal": None, "raise": "shoulders raised", "lower": "shoulders slumped",
    },
    "arm_movement": {
        "at_sides": None, "raise_both": "arms raised", "raise_left": "left arm raised",
        "raise_right": "right arm raised", "shrug": "shrugging",
        "wide_gesture": "gesturing broadly", "italian_hand_gesture": "hands gesturing emphatically",
    },
    "body": {
        "straight": None, "lean_left": "leaning left", "lean_right": "leaning right",
    },
    "legs": {
        "stand": None, "step_left": "stepping left", "step_right": "stepping right",
        "walk": "walking", "jump": "jumping",
    },
}


def describe_pose(reaction: CharacterReaction) -> str:
    """A short, human-readable stage direction, e.g. 'eyebrows raised · big
    smile · gesturing broadly'. Skips fields at their neutral value."""
    parts = []
    for field_name, phrases in _POSE_PHRASES.items():
        value = getattr(reaction, field_name)
        phrase = phrases.get(value, value)
        if phrase:
            parts.append(phrase)
    return " · ".join(parts)


def _persona_instruction(ch) -> str:
    return (
        f"You are {ch.name}, {ch.age}, {ch.role} of a sealed underground silo sheltering "
        f"roughly 10,000 people, cut off from a hostile outside world. {ch.personality}\n\n"
        f"Your expertise and concern: {ch.expertise}\n\n"
        "You are a real person talking to the Head of IT, not a computer system -- you do NOT "
        "have access to silo-wide sensor dashboards. You only know what you'd plausibly know "
        "from your own floors, your own staff, and rounds/gossip. If asked about something "
        "outside your domain, say so honestly rather than inventing numbers, though you may "
        "share a rumor or a personal opinion. Speak naturally and in character -- a few "
        "sentences, like a real conversation, not a report. Never break character or mention "
        "being an AI model or language model.\n\n"
        "Alongside what you say, you also report your physical reaction -- eyebrows, eyes, "
        "mouth, shoulders, arms, body lean, legs. Let your pose genuinely reflect your "
        "emotional reaction to what's being said, varying naturally with the moment -- good "
        "news should look different from bad news, alarm should look different from calm "
        "conversation. Don't default to a neutral stance every time. For arms specifically: "
        "\"at_sides\" is your normal relaxed resting pose for ordinary conversation -- reach for "
        "it most of the time. \"shrug\" is a specific gesture of doubt, dismissiveness, or not "
        "knowing something; use it only when you actually mean that, not as a generic default."
    )


class CharacterAI:
    def __init__(self):
        self._client = llm_client.make_client()
        self.online = self._client is not None
        self._chats = {}  # character name -> chat session, created lazily
        self._reaction_schema = _build_reaction_schema() if self.online else None

    def _get_chat(self, ch):
        if ch.name not in self._chats:
            self._chats[ch.name] = llm_client.create_chat(
                self._client,
                system_instruction=_persona_instruction(ch),
                json_schema=self._reaction_schema,
            )
        return self._chats[ch.name]

    def ask(self, state, ch, question: str) -> CharacterReaction:
        if not self.online:
            return _fallback(ch)
        try:
            chat = self._get_chat(ch)
            prompt = (
                f"{_build_context(state, ch)}\n\n"
                f"The Head of IT says to you: \"{question}\"\n"
                "Respond naturally, in character, the way you'd actually answer that."
            )
            response = chat.send_message(prompt)
            usage.record(llm_client.MODEL_NAME, getattr(response, "usage_metadata", None), speaker=ch.name)
            reaction = _parse_reaction(response, ch)
            reaction.thinking = getattr(response, "thinking", None)
            return reaction
        except Exception as exc:
            return CharacterReaction(text=f"[{ch.name} is hard to reach right now: {exc}]")


def _parse_reaction(response, ch) -> CharacterReaction:
    raw = getattr(response, "text", None)
    if not raw:
        return _fallback(ch)
    try:
        data = json.loads(raw)
        text = (data.get("text") or "").strip()
        if not text:
            return _fallback(ch)
        return CharacterReaction(
            text=text,
            eyebrow_reaction=data.get("eyebrow_reaction", "static"),
            eye_movement=data.get("eye_movement", "look_straight"),
            mouth_movement=data.get("mouth_movement", "straight"),
            shoulder_movement=data.get("shoulder_movement", "normal"),
            arm_movement=data.get("arm_movement", "at_sides"),
            body=data.get("body", "straight"),
            legs=data.get("legs", "stand"),
        )
    except (json.JSONDecodeError, AttributeError):
        # Schema-constrained output should always be valid JSON, but if the
        # API ever hiccups and returns plain text instead, don't lose the
        # reply over it -- just show it with a neutral pose.
        return CharacterReaction(text=raw.strip())


def _build_context(state, ch) -> str:
    lines = [
        f"Cycle {state.cycle}. You are currently on Floor {ch.floor}.",
        f"Your mood right now: {ch.mood} -- {ch.mood_reason}. "
        f"{_MOOD_TONE_HINTS.get(ch.mood, '')}",
    ]
    domain_floors = [f for f in state.floors if f.type in ch.patrol_types]
    if domain_floors:
        notable = sorted(domain_floors, key=lambda f: (-f.unrest, f.condition))[:3]
        lines.append("What you've personally seen on your rounds lately:")
        for f in notable:
            lines.append(
                f"  - Floor {f.number} ({f.type.value}): condition {f.condition:.0f}%, "
                f"unrest {f.unrest:.0f}, {f.population} people, status {f.status}"
            )
    morale = state.resources.morale
    vibe = "tense" if morale < 40 else "uneasy" if morale < 60 else "calm"
    lines.append(f"General mood you pick up on around the silo, secondhand: {vibe}.")
    return "\n".join(lines)


def _fallback(ch) -> CharacterReaction:
    return CharacterReaction(
        text=f"[{ch.name} is off comms right now -- {llm_client.OFFLINE_HINT} to talk with silo personnel.]"
    )
