"""Random events and unrest/riot resolution."""

import random

from game import constants as C
from game.models import FloorType, SiloState

NON_RESIDENTIAL_SYSTEM_TYPES = [
    FloorType.FARM,
    FloorType.POWER_PLANT,
    FloorType.OXYGEN_GARDEN,
    FloorType.WATER_TREATMENT,
    FloorType.MEDICAL,
    FloorType.MAINTENANCE,
]


def roll_random_events(state: SiloState) -> list:
    """Chance-based flavor/mechanical events, independent of the resource
    shortage events already produced by advance_cycle."""
    events = []

    if random.random() < 0.22:
        events.append(_equipment_failure(state))

    if random.random() < 0.10:
        events.append(_sickness_outbreak(state))

    if random.random() < 0.06:
        events.append(_it_sabotage(state))

    if random.random() < 0.05:
        events.append(_scavenged_supplies(state))

    if random.random() < 0.08:
        events.append(_black_market(state))

    return [e for e in events if e]


def _equipment_failure(state: SiloState) -> str:
    candidates = [f for f in state.floors if f.type in NON_RESIDENTIAL_SYSTEM_TYPES]
    if not candidates:
        return ""
    floor = random.choice(candidates)
    drop = random.uniform(10, 28)
    floor.condition = max(0.0, floor.condition - drop)
    floor.note(f"Equipment failure (-{drop:.0f} condition)")
    return (
        f"Equipment failure on Floor {floor.number} ({floor.type.value}): "
        f"condition down to {floor.condition:.0f}%."
    )


def _sickness_outbreak(state: SiloState) -> str:
    candidates = [f for f in state.floors if f.population > 0]
    if not candidates:
        return ""
    floor = random.choice(candidates)
    severity = random.uniform(8, 20)
    floor.health = max(0.0, floor.health - severity)
    floor.note(f"Sickness outbreak (-{severity:.0f} health)")
    medical = state.floors_of_type(FloorType.MEDICAL)
    med_strength = sum(f.condition for f in medical) / max(1, len(medical) * 100)
    state.resources.health = max(0.0, state.resources.health - severity * (1 - med_strength) * 0.15)
    return f"Sickness outbreak reported on Floor {floor.number} ({floor.type.value})."


def _it_sabotage(state: SiloState) -> str:
    it_floors = state.floors_of_type(FloorType.IT_DEPARTMENT)
    if not it_floors:
        return ""
    floor = it_floors[0]
    drop = random.uniform(10, 25)
    floor.condition = max(0.0, floor.condition - drop)
    floor.note("Suspicious intrusion attempt on IT systems")
    return (
        "Anomaly detected: someone attempted to breach silo control systems through "
        "the IT network. Surveillance and rationing systems may be compromised until reviewed."
    )


def _scavenged_supplies(state: SiloState) -> str:
    bonus_food = random.uniform(500, 1500)
    bonus_fuel = random.uniform(50, 200)
    state.resources.food += bonus_food
    state.resources.fuel += bonus_fuel
    return f"Maintenance crews recovered {bonus_food:.0f} food units and {bonus_fuel:.0f} fuel units from old storage."


def _black_market(state: SiloState) -> str:
    market_floors = state.floors_of_type(FloorType.MARKET)
    if not market_floors:
        return ""
    loss = random.uniform(100, 400)
    state.resources.food = max(0.0, state.resources.food - loss)
    state.resources.morale = min(100.0, state.resources.morale + 1.5)
    return f"Black market trading reported near the Market floors: {loss:.0f} food units diverted, but morale ticked up."


def update_unrest_and_riots(state: SiloState) -> list:
    """Update per-floor unrest from silo-wide stability/morale, and resolve
    riots on floors that cross the threshold."""
    events = []
    res = state.resources

    base_pressure = (100 - res.stability) * 0.3 + (100 - res.morale) * 0.2
    for f in state.floors:
        if f.population <= 0:
            continue
        drift = base_pressure * random.uniform(0.6, 1.2) * 0.1
        f.unrest = max(0.0, min(100.0, f.unrest + drift - 1.0))

        if f.unrest >= C.RIOT_LOCAL_UNREST_THRESHOLD and res.stability < C.RIOT_STABILITY_THRESHOLD:
            events.append(_riot(state, f))

    return events


def _riot(state, floor) -> str:
    casualties = max(1, int(floor.population * random.uniform(0.01, 0.03)))
    floor.population = max(0, floor.population - casualties)
    floor.condition = max(0.0, floor.condition - random.uniform(15, 35))
    floor.unrest = 40.0
    state.resources.stability = max(0.0, state.resources.stability - 8)
    state.resources.morale = max(0.0, state.resources.morale - 5)
    state.population = sum(f.population for f in state.floors)
    return (
        f"RIOT on Floor {floor.number} ({floor.type.value}): security response required. "
        f"{casualties} casualties, infrastructure damaged."
    )
