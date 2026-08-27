"""The Continuity Protocol: the Silo AI's own fail-safe.

The AI advises, but it is not *only* an advisor -- if stability or morale
stay critical too long, it is authorized to act on the population directly,
no further sign-off required. This module is the mechanical half of that
threat; game/ai_advisor.py supplies the voice.

Escalation ladder:
  1. ARM   -- stability/morale cross the danger threshold. A countdown starts.
  2. CLEAR -- both recover above the (higher) clear threshold before the
              deadline: the AI stands down.
  3. CULL  -- the deadline passes without recovery: the AI removes a chunk
              of population itself, concentrated on the most unstable
              floors. This buys order but costs morale/health -- it is a
              trap, not a fix. The countdown then restarts.
  4. An immediate, unconditional cull-equivalent also fires if stability
     and morale hit zero simultaneously, and repeated culls culminate in
     full termination -- both are game overs, set via state.game_over.
"""

import random

from game import constants as C
from game.models import SiloState


def evaluate(state: SiloState) -> list:
    """Advance the Continuity Protocol by one cycle. Returns narrative
    event strings (in the AI's voice) describing anything it did."""
    events = []
    res = state.resources

    if res.stability <= 0 and res.morale <= 0:
        events.append(_terminate(state, "Stability and morale collapsed simultaneously."))
        return events

    danger = res.stability < C.PROTOCOL_ARM_STABILITY or res.morale < C.PROTOCOL_ARM_MORALE
    safe = res.stability >= C.PROTOCOL_CLEAR_STABILITY and res.morale >= C.PROTOCOL_CLEAR_MORALE

    if not state.protocol_armed:
        if danger:
            state.protocol_armed = True
            state.protocol_deadline_cycle = state.cycle + C.PROTOCOL_GRACE_CYCLES
            events.append(_arm_message(state))
        return events

    # Already armed.
    if safe:
        state.protocol_armed = False
        state.protocol_deadline_cycle = None
        events.append(
            "Continuity Protocol stood down. Silo metrics within acceptable parameters. "
            "Good work, Head of IT."
        )
        return events

    if state.cycle >= state.protocol_deadline_cycle:
        events.append(_execute_cull(state))
        if state.game_over:
            return events
        # The clock resets; if the underlying problem isn't fixed, it fires again.
        state.protocol_deadline_cycle = state.cycle + C.PROTOCOL_GRACE_CYCLES

    return events


def _arm_message(state: SiloState) -> str:
    res = state.resources
    return (
        f"CONTINUITY PROTOCOL ARMED. Stability {res.stability:.0f}/100, morale {res.morale:.0f}/100 "
        f"-- below acceptable parameters. You have {C.PROTOCOL_GRACE_CYCLES} cycles to correct course. "
        "If you cannot, I will."
    )


def _execute_cull(state: SiloState) -> str:
    res = state.resources
    fraction = min(
        C.PROTOCOL_CULL_FRACTION_MAX,
        C.PROTOCOL_CULL_FRACTION_BASE + state.culls_executed * C.PROTOCOL_CULL_ESCALATION_PER_PRIOR,
    )
    target = max(1, int(state.population * fraction))
    removed, floors_hit = _remove_population(state, target)

    state.culls_executed += 1
    res.stability = min(100.0, res.stability + C.PROTOCOL_CULL_STABILITY_RELIEF)
    res.morale = max(0.0, res.morale - C.PROTOCOL_CULL_MORALE_COST)
    res.health = max(0.0, res.health - C.PROTOCOL_CULL_HEALTH_COST)

    floor_list = ", ".join(f"#{n}" for n in floors_hit[:8])
    message = (
        f"CONTINUITY PROTOCOL ENFORCED. Corrective deadline passed without resolution. "
        f"{removed} residents removed from floors {floor_list}, prioritized by unrest. "
        f"This was avoidable. Stability restored to {res.stability:.0f}; I note morale has not improved."
    )

    if state.culls_executed >= C.PROTOCOL_MAX_CULLS_BEFORE_TERMINATION:
        return _terminate(
            state,
            f"{state.culls_executed} corrective actions have failed to stabilize the silo.",
            prior_message=message,
        )
    return message


def _remove_population(state: SiloState, target: int):
    ordered = sorted(
        (f for f in state.floors if f.population > 0),
        key=lambda f: f.unrest,
        reverse=True,
    )
    removed = 0
    floors_hit = []
    while removed < target and ordered:
        progressed = False
        for f in ordered:
            if removed >= target:
                break
            if f.population <= 0:
                continue
            take = min(f.population, max(1, (target - removed + 2) // 3))
            f.population -= take
            removed += take
            progressed = True
            if f.number not in floors_hit:
                floors_hit.append(f.number)
        ordered = [f for f in ordered if f.population > 0]
        if not progressed:
            break
    state.population = sum(f.population for f in state.floors)
    return removed, floors_hit


def _terminate(state: SiloState, cause: str, prior_message: str = "") -> str:
    state.game_over = True
    state.game_over_reason = (
        "CONTINUITY PROTOCOL: TERMINAL.\n\n"
        f"{cause}\n\n"
        "The Silo AI's voice does not change register: \"Corrective measures have "
        "repeatedly failed to restore acceptable parameters. Statistical models "
        "indicate this population now endangers the Silo's long-term continuity. "
        "Initiating full reset.\"\n\n"
        "Every door seals. Every system you spent your directives protecting turns "
        "against the people inside it. You were the one system the AI still needed "
        "a human for -- and it never needed you for long."
    )
    header = "TERMINATION SEQUENCE INITIATED. " + cause
    return f"{prior_message}\n\n{header}" if prior_message else header
