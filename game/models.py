"""Core data model for the silo: floors, resources, and overall state."""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class FloorType(str, Enum):
    RESIDENTIAL = "Residential"
    FARM = "Hydroponic Farm"
    CAFETERIA = "Cafeteria"
    POWER_PLANT = "Power Plant"
    OXYGEN_GARDEN = "Oxygen Garden"
    WATER_TREATMENT = "Water Treatment"
    MEDICAL = "Medical Bay"
    SECURITY = "Security HQ"
    MAINTENANCE = "Maintenance Bay"
    MARKET = "Market"
    SCHOOL = "School"
    IT_DEPARTMENT = "IT Department"
    STORAGE = "Storage"


@dataclass
class Floor:
    number: int
    type: FloorType
    population: int = 0
    condition: float = 100.0   # equipment/infrastructure condition, 0-100
    unrest: float = 0.0        # local unrest, 0-100 (riot risk on this floor)
    health: float = 100.0      # local health/sickness level, 0-100
    log: list = field(default_factory=list)  # recent event strings

    @property
    def status(self) -> str:
        if self.condition < 30:
            return "CRITICAL"
        if self.condition < 60:
            return "DEGRADED"
        return "NOMINAL"

    def note(self, message: str) -> None:
        self.log.append(message)
        self.log = self.log[-5:]


@dataclass
class Character:
    """A named person the player can see moving around the silo, and can
    talk to -- an LLM persona scoped to their own domain and mood, distinct
    from the Silo AI's silo-wide sensor access. Position is visual flavor;
    mood and personality drive their chat responses."""
    name: str
    role: str
    color: str            # hex accent color for their marker
    initials: str
    avatar: str = "🧑"     # emoji, used as their chat avatar (st.chat_message needs an emoji, not text)
    floor: int = 1
    personality: str = ""              # persona description for their system prompt
    expertise: str = ""                # what they know deeply and care about
    patrol_types: list = field(default_factory=list)  # list[FloorType], where they're drawn to
    mood: str = "happy"                # happy | grumpy | concerned | frustrated | tired | hungry
    mood_reason: str = ""              # short human-readable cause, shown in UI and fed to their prompt

    # Fixed appearance -- who they are, not how they're currently feeling.
    age: int = 40
    hair_style: str = "short"          # short | buzz | bun | long
    hair_color: str = "#3a2a1f"
    facial_hair: str = "none"          # none | mustache | beard


@dataclass
class Resources:
    food: float
    water: float
    oxygen: float
    fuel: float
    power_ratio: float = 1.0   # last cycle's supply/demand ratio, 0-1+
    morale: float = 65.0       # silo-wide morale, 0-100
    stability: float = 70.0    # silo-wide order/security, 0-100 (low = riot risk)
    health: float = 85.0       # silo-wide public health, 0-100


@dataclass
class SiloState:
    cycle: int
    population: int
    floors: list  # list[Floor], index 0 == floor 1
    resources: Resources
    ration_level: str = "normal"
    power_priority: str = "balanced"  # balanced | life_support | residential | security
    history: list = field(default_factory=list)  # list[str] event log across cycles
    game_over: bool = False
    game_over_reason: str = ""

    # Continuity Protocol: the Silo AI's own fail-safe. Armed when stability
    # or morale stay critical too long; if not resolved before the deadline,
    # the AI executes a population "cull" itself rather than waiting for
    # natural collapse. See game/failsafe.py.
    protocol_armed: bool = False
    protocol_deadline_cycle: Optional[int] = None
    culls_executed: int = 0

    characters: list = field(default_factory=list)  # list[Character]

    def floor(self, number: int) -> Floor:
        return self.floors[number - 1]

    def floors_of_type(self, ftype: FloorType):
        return [f for f in self.floors if f.type == ftype]

    def log(self, message: str) -> None:
        self.history.append(f"[Cycle {self.cycle}] {message}")
        self.history = self.history[-50:]
