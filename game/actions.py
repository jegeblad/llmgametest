"""Player-facing directives, issued through the IT control systems."""

from game import constants as C
from game.models import FloorType, SiloState


class ActionError(Exception):
    pass


def dispatch_maintenance(state: SiloState, floor_number: int) -> str:
    maintenance_floors = state.floors_of_type(FloorType.MAINTENANCE)
    if not maintenance_floors:
        raise ActionError("No maintenance crews available.")
    try:
        floor = state.floor(floor_number)
    except IndexError:
        raise ActionError(f"No such floor: {floor_number}")

    crew_strength = sum(f.condition for f in maintenance_floors) / (100.0 * len(maintenance_floors))
    repair = C.MAINTENANCE_REPAIR_PER_CREW * max(0.3, crew_strength)
    floor.condition = min(100.0, floor.condition + repair)
    floor.note(f"Maintenance dispatched (+{repair:.0f} condition)")
    msg = f"Maintenance crew dispatched to Floor {floor_number} ({floor.type.value}): condition now {floor.condition:.0f}%."
    state.log(msg)
    return msg


def deploy_security(state: SiloState, floor_number: int) -> str:
    security_floors = state.floors_of_type(FloorType.SECURITY)
    if not security_floors:
        raise ActionError("No security units available.")
    try:
        floor = state.floor(floor_number)
    except IndexError:
        raise ActionError(f"No such floor: {floor_number}")

    reduction = C.SECURITY_UNREST_REDUCTION
    floor.unrest = max(0.0, floor.unrest - reduction)
    # Heavy-handed security nudges morale down even as it restores order.
    state.resources.morale = max(0.0, state.resources.morale - 1.0)
    state.resources.stability = min(100.0, state.resources.stability + 2.0)
    floor.note(f"Security deployed (-{reduction:.0f} unrest)")
    msg = f"Security deployed to Floor {floor_number} ({floor.type.value}): unrest down to {floor.unrest:.0f}."
    state.log(msg)
    return msg


def set_ration_level(state: SiloState, level: str) -> str:
    if level not in C.RATION_LEVELS:
        raise ActionError(f"Unknown ration level '{level}'. Options: {', '.join(C.RATION_LEVELS)}")
    state.ration_level = level
    msg = f"Rationing set to '{level}'."
    state.log(msg)
    return msg


def set_power_priority(state: SiloState, priority: str) -> str:
    if priority not in C.POWER_PRIORITIES:
        raise ActionError(f"Unknown power priority '{priority}'. Options: {', '.join(C.POWER_PRIORITIES)}")
    state.power_priority = priority
    msg = f"Power routing priority set to '{priority}'."
    state.log(msg)
    return msg


def broadcast_announcement(state: SiloState, tone: str) -> str:
    if tone not in C.BROADCAST_TONES:
        raise ActionError(f"Unknown broadcast tone '{tone}'. Options: {', '.join(C.BROADCAST_TONES)}")
    delta = C.BROADCAST_TONES[tone]
    state.resources.morale = min(100.0, max(0.0, state.resources.morale + delta))
    msg = f"Silo-wide broadcast sent (tone: {tone}). Morale shifted by {delta:+.1f}."
    state.log(msg)
    return msg


def lockdown_floor(state: SiloState, floor_number: int, engage: bool) -> str:
    try:
        floor = state.floor(floor_number)
    except IndexError:
        raise ActionError(f"No such floor: {floor_number}")
    if engage:
        floor.unrest = max(0.0, floor.unrest - 10.0)
        state.resources.morale = max(0.0, state.resources.morale - 2.0)
        floor.note("Lockdown engaged")
        msg = f"Floor {floor_number} ({floor.type.value}) locked down. Movement restricted."
    else:
        floor.note("Lockdown lifted")
        msg = f"Lockdown on Floor {floor_number} ({floor.type.value}) lifted."
    state.log(msg)
    return msg
