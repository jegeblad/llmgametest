"""Silo setup and the per-cycle resource/production simulation."""

import random

from game import characters
from game import constants as C
from game.models import Floor, FloorType, Resources, SiloState


def init_silo() -> SiloState:
    floors = []
    number = 1

    # Lay out floor types roughly interleaved rather than blocked together,
    # so e.g. farms and medical bays aren't all clustered at the top.
    type_pool = []
    for ftype, count in C.FLOOR_DISTRIBUTION.items():
        type_pool.extend([ftype] * count)
    rng = random.Random(42)
    rng.shuffle(type_pool)

    for ftype in type_pool:
        staff = C.FLOOR_STAFFING.get(ftype)
        pop = staff if staff is not None else 0  # residential filled below
        floors.append(Floor(number=number, type=ftype, population=pop))
        number += 1

    residential_floors = [f for f in floors if f.type == FloorType.RESIDENTIAL]
    assigned = sum(f.population for f in floors)
    remaining = C.STARTING_POPULATION - assigned
    base = remaining // len(residential_floors)
    extra = remaining % len(residential_floors)
    for i, f in enumerate(residential_floors):
        f.population = base + (1 if i < extra else 0)

    resources = Resources(
        food=C.STARTING_RESERVES["food"],
        water=C.STARTING_RESERVES["water"],
        oxygen=C.STARTING_RESERVES["oxygen"],
        fuel=C.STARTING_RESERVES["fuel"],
        morale=C.STARTING_MORALE,
        stability=C.STARTING_STABILITY,
        health=C.STARTING_HEALTH,
    )

    total_pop = sum(f.population for f in floors)
    state = SiloState(cycle=0, population=total_pop, floors=floors, resources=resources)
    state.characters = characters.spawn(state)
    characters.compute_moods(state)
    state.log(f"Silo sealed. {total_pop} souls aboard across {C.NUM_FLOORS} floors.")
    return state


def _avg_condition(floors) -> float:
    if not floors:
        return 100.0
    return sum(f.condition for f in floors) / len(floors)


def _power_priority_multiplier(state: SiloState, ftype: FloorType) -> float:
    """Power routing preference nudges which systems get supply first
    when total power is insufficient."""
    priority = state.power_priority
    life_support = {FloorType.FARM, FloorType.OXYGEN_GARDEN, FloorType.WATER_TREATMENT}
    if priority == "life_support":
        return 1.15 if ftype in life_support else 0.85
    if priority == "residential":
        return 1.2 if ftype == FloorType.RESIDENTIAL else 0.92
    if priority == "security":
        return 1.3 if ftype == FloorType.SECURITY else 0.9
    return 1.0


def advance_cycle(state: SiloState) -> list:
    """Advance the silo by one cycle (day). Returns a list of human-readable
    event strings describing what happened, for display and for the AI."""
    events = []
    state.cycle += 1
    res = state.resources
    pop = sum(f.population for f in state.floors)
    state.population = pop

    # --- Power ---
    power_plants = state.floors_of_type(FloorType.POWER_PLANT)
    power_supply = sum(
        C.POWER_FLOOR_OUTPUT * (f.condition / 100.0) for f in power_plants
    )
    fuel_needed = len(power_plants) * C.FUEL_PER_POWER_FLOOR
    if res.fuel < fuel_needed and fuel_needed > 0:
        shortfall_ratio = max(0.0, res.fuel / fuel_needed)
        power_supply *= shortfall_ratio
        res.fuel = max(0.0, res.fuel - res.fuel)
        events.append("Fuel reserves critically low: reactor output throttled.")
    else:
        res.fuel -= fuel_needed

    power_demand = 0.0
    for f in state.floors:
        base_demand = C.FLOOR_POWER_DEMAND.get(f.type, 5)
        power_demand += base_demand * _power_priority_multiplier(state, f.type)
    power_ratio = min(1.3, power_supply / power_demand) if power_demand else 1.0
    res.power_ratio = power_ratio

    # --- Food (farms) ---
    farms = state.floors_of_type(FloorType.FARM)
    food_production = sum(
        C.FARM_FLOOR_YIELD * (f.condition / 100.0) for f in farms
    ) * min(1.0, power_ratio)
    ration = C.RATION_LEVELS[state.ration_level]
    food_consumption = pop * C.FOOD_PER_PERSON * ration["multiplier"]
    res.food += food_production - food_consumption

    # --- Water ---
    water_plants = state.floors_of_type(FloorType.WATER_TREATMENT)
    water_production = sum(
        C.WATER_FLOOR_YIELD * (f.condition / 100.0) for f in water_plants
    ) * min(1.0, power_ratio)
    water_consumption = pop * C.WATER_PER_PERSON * ration["multiplier"]
    res.water += water_production - water_consumption

    # --- Oxygen ---
    o2_gardens = state.floors_of_type(FloorType.OXYGEN_GARDEN)
    oxygen_production = sum(
        C.OXYGEN_FLOOR_YIELD * (f.condition / 100.0) for f in o2_gardens
    ) * min(1.0, power_ratio)
    oxygen_consumption = pop * C.OXYGEN_PER_PERSON
    res.oxygen += oxygen_production - oxygen_consumption

    # --- Shortage penalties ---
    def shortage_hit(resource_name, value):
        if value < 0:
            events.append(
                f"{resource_name} reserves hit zero — rationing failures reported on several floors."
            )
            return True
        return False

    starving = shortage_hit("Food", res.food)
    dehydrated = shortage_hit("Water", res.water)
    suffocating = shortage_hit("Oxygen", res.oxygen)
    res.food = max(0.0, res.food)
    res.water = max(0.0, res.water)
    res.oxygen = max(0.0, res.oxygen)

    morale_delta = ration["morale_delta"] - C.BASELINE_MORALE_DECAY
    stability_delta = -C.BASELINE_STABILITY_DECAY
    health_delta = 0.1  # slow natural recovery

    if starving:
        morale_delta -= 6
        stability_delta -= 5
        health_delta -= 3
    if dehydrated:
        morale_delta -= 5
        stability_delta -= 4
        health_delta -= 2
    if suffocating:
        morale_delta -= 10
        stability_delta -= 8
        health_delta -= 6
        # Oxygen deprivation directly costs lives.
        deaths = max(1, int(pop * 0.004))
        _apply_deaths(state, deaths)
        events.append(f"Oxygen shortage: {deaths} confirmed deaths silo-wide.")

    if power_ratio < 0.7:
        morale_delta -= 2
        events.append(f"Power output at {power_ratio*100:.0f}% of demand — brownouts across the silo.")

    # low buffers create anxiety even before hitting zero
    if 0 <= res.food < pop * C.FOOD_PER_PERSON * 3:
        morale_delta -= 1.5
    if 0 <= res.oxygen < pop * C.OXYGEN_PER_PERSON * 2:
        morale_delta -= 2.5
        stability_delta -= 1.5

    res.morale = _clamp(res.morale + morale_delta)
    res.stability = _clamp(res.stability + stability_delta)
    res.health = _clamp(res.health + health_delta)

    return events


def _apply_deaths(state: SiloState, count: int) -> None:
    remaining = count
    weighted = list(state.floors)
    random.shuffle(weighted)
    for f in weighted:
        if remaining <= 0:
            break
        if f.population <= 0:
            continue
        take = min(f.population, max(1, remaining // max(1, len(weighted))), remaining)
        f.population -= take
        remaining -= take
    state.population = sum(f.population for f in state.floors)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))
