"""Tunable constants for the silo simulation."""

from game.models import FloorType

NUM_FLOORS = 200
STARTING_POPULATION = 10_000

# How many floors of each type exist in the silo. Must sum to NUM_FLOORS.
FLOOR_DISTRIBUTION = {
    FloorType.RESIDENTIAL: 140,
    FloorType.FARM: 14,
    FloorType.CAFETERIA: 10,
    FloorType.POWER_PLANT: 3,
    FloorType.OXYGEN_GARDEN: 6,
    FloorType.WATER_TREATMENT: 5,
    FloorType.MEDICAL: 6,
    FloorType.SECURITY: 4,
    FloorType.MAINTENANCE: 5,
    FloorType.MARKET: 4,
    FloorType.SCHOOL: 2,
    FloorType.IT_DEPARTMENT: 1,
}
assert sum(FLOOR_DISTRIBUTION.values()) == NUM_FLOORS

# Staff/occupants stationed on each non-residential floor (per floor).
FLOOR_STAFFING = {
    FloorType.FARM: 40,
    FloorType.CAFETERIA: 15,
    FloorType.POWER_PLANT: 25,
    FloorType.OXYGEN_GARDEN: 20,
    FloorType.WATER_TREATMENT: 20,
    FloorType.MEDICAL: 30,
    FloorType.SECURITY: 35,
    FloorType.MAINTENANCE: 25,
    FloorType.MARKET: 15,
    FloorType.SCHOOL: 20,
    FloorType.IT_DEPARTMENT: 15,
}

# Power demand per floor per day, by floor type.
FLOOR_POWER_DEMAND = {
    FloorType.RESIDENTIAL: 5,
    FloorType.FARM: 80,
    FloorType.CAFETERIA: 20,
    FloorType.POWER_PLANT: 10,
    FloorType.OXYGEN_GARDEN: 90,
    FloorType.WATER_TREATMENT: 60,
    FloorType.MEDICAL: 40,
    FloorType.SECURITY: 30,
    FloorType.MAINTENANCE: 20,
    FloorType.MARKET: 15,
    FloorType.SCHOOL: 10,
    FloorType.IT_DEPARTMENT: 25,
    FloorType.STORAGE: 5,
}

# Per-person daily consumption.
FOOD_PER_PERSON = 1.0
WATER_PER_PERSON = 1.0
OXYGEN_PER_PERSON = 1.0

# Per-floor daily output at 100% condition and full power availability.
# Tuned so each life-support system runs a modest (~10-15%) surplus over
# baseline demand at full population, normal rationing, undamaged floors --
# enough margin to absorb a floor or two going down before it bites, but not
# so much that degradation/rationing/power routing stop mattering.
FARM_FLOOR_YIELD = 800.0       # food units/day   (14 floors => 11,200 vs ~10,000 demand)
WATER_FLOOR_YIELD = 2300.0     # water units/day  (5 floors => 11,500 vs ~10,000 demand)
OXYGEN_FLOOR_YIELD = 1900.0    # oxygen units/day (6 floors => 11,400 vs ~10,000 demand)
POWER_FLOOR_OUTPUT = 1300.0    # power units/day  (3 floors => 3,900 vs ~3,450 demand)
FUEL_PER_POWER_FLOOR = 8.0     # fuel units consumed/day per operating plant

# Starting reserves: a real buffer (roughly 1-2 weeks at full population)
# against shortfalls, separate from the ongoing production/consumption
# balance above. Fuel has no production at all -- it is the one resource
# that only ever depletes, occasionally topped up by rare salvage events.
STARTING_RESERVES = {
    "food": 100_000.0,
    "water": 100_000.0,
    "oxygen": 80_000.0,
    "fuel": 4_000.0,
}

STARTING_MORALE = 65.0
STARTING_STABILITY = 70.0
STARTING_HEALTH = 85.0

# Baseline per-cycle drain applied every cycle regardless of resource
# shortages -- confinement, close quarters, and no sky take a toll on their
# own. Left unmanaged, this alone arms the Continuity Protocol within a few
# weeks; only active intervention (broadcasts especially, for morale) can
# outpace it. Tuned so the silo cannot simply be left running unattended.
BASELINE_MORALE_DECAY = 2.0
BASELINE_STABILITY_DECAY = 1.0

# Ration levels the player can set: multiplier on per-person consumption
# and a rough morale effect per cycle while active.
RATION_LEVELS = {
    "generous": {"multiplier": 1.15, "morale_delta": 0.4},
    "normal": {"multiplier": 1.0, "morale_delta": 0.0},
    "tight": {"multiplier": 0.85, "morale_delta": -0.6},
    "emergency": {"multiplier": 0.6, "morale_delta": -1.5},
}

MAINTENANCE_REPAIR_PER_CREW = 25.0  # condition points restored per dispatch
SECURITY_UNREST_REDUCTION = 20.0    # unrest points reduced per deployment

POWER_PRIORITIES = ["balanced", "life_support", "residential", "security"]
BROADCAST_TONES = {
    "reassure": 3.0,
    "honest": 1.0,
    "warn": -1.0,
}

RIOT_STABILITY_THRESHOLD = 35.0
RIOT_LOCAL_UNREST_THRESHOLD = 70.0

# --- Continuity Protocol: the Silo AI's fail-safe ---
# Arms when stability or morale drops below these levels...
PROTOCOL_ARM_STABILITY = 40.0
PROTOCOL_ARM_MORALE = 35.0
# ...and disarms only once both climb back above these (hysteresis, so it
# doesn't flicker on/off at the boundary).
PROTOCOL_CLEAR_STABILITY = 50.0
PROTOCOL_CLEAR_MORALE = 45.0
# Cycles the Head of IT has to fix things once armed before the AI acts.
PROTOCOL_GRACE_CYCLES = 3
# Fraction of population removed per cull, escalating with each repeat --
# concentrated on the highest-unrest floors first.
PROTOCOL_CULL_FRACTION_BASE = 0.05
PROTOCOL_CULL_FRACTION_MAX = 0.12
PROTOCOL_CULL_ESCALATION_PER_PRIOR = 0.03
# A cull restores order but is not a strategy: it costs morale/health even
# as it relieves stability, and enough of them end the game outright.
PROTOCOL_CULL_STABILITY_RELIEF = 18.0
PROTOCOL_CULL_MORALE_COST = 10.0
PROTOCOL_CULL_HEALTH_COST = 5.0
PROTOCOL_MAX_CULLS_BEFORE_TERMINATION = 3
