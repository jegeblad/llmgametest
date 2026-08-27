"""Named personnel who move around the silo each cycle and can be talked to.

Movement is visual flavor. Mood is not: each character's mood is derived
every cycle from a distress score scoped to their own domain (medical
conditions for the doctor, unrest for security, and so on), plus a couple
of silo-wide overrides (emergency rations make everyone hungry; poor public
health makes people tired). game/character_ai.py uses the resulting mood
and reason to color how they actually talk.
"""

import random

from game.models import Character, FloorType

_SYSTEMS_TYPES = [FloorType.FARM, FloorType.POWER_PLANT, FloorType.WATER_TREATMENT,
                  FloorType.OXYGEN_GARDEN, FloorType.MAINTENANCE, FloorType.IT_DEPARTMENT]
_RESIDENTIAL_TYPES = [FloorType.RESIDENTIAL, FloorType.MARKET, FloorType.SCHOOL]


def _distress_medical(state):
    med_floors = [f for f in state.floors if f.type == FloorType.MEDICAL]
    base = 100 - state.resources.health
    if med_floors:
        worst = min(med_floors, key=lambda f: f.condition)
        if worst.condition < 50:
            base += (60 - worst.condition) * 0.5
            return min(100, max(0, base)), f"the medical bay on Floor {worst.number} is barely holding together"
    if state.resources.health < 60:
        return min(100, max(0, base)), "public health across the silo keeps sliding"
    return min(100, max(0, base)), "patients are stable and the wards are quiet"


def _distress_security(state):
    sec_floors = [f for f in state.floors if f.type == FloorType.SECURITY]
    base = 100 - state.resources.stability
    if sec_floors:
        worst = max(sec_floors, key=lambda f: f.unrest)
        if worst.unrest >= 40:
            base += worst.unrest * 0.3
            return min(100, max(0, base)), f"unrest is rising on Floor {worst.number}, under his watch"
    if state.resources.stability < 50:
        return min(100, max(0, base)), "order feels thin across the silo lately"
    return min(100, max(0, base)), "the floors are quiet and nobody's testing him"


def _distress_engineering(state):
    sys_floors = [f for f in state.floors if f.type in _SYSTEMS_TYPES]
    avg_cond = sum(f.condition for f in sys_floors) / len(sys_floors) if sys_floors else 100
    power_shortfall = max(0.0, 1.0 - state.resources.power_ratio) * 100
    score = min(100, max(0, (100 - avg_cond) * 0.6 + power_shortfall * 0.4))
    if sys_floors:
        worst = min(sys_floors, key=lambda f: f.condition)
        if worst.condition < 50:
            return score, f"Floor {worst.number} ({worst.type.value}) is held together with hope and spare parts"
    if power_shortfall > 10:
        return score, "power output isn't keeping up with demand"
    return score, "the machines are behaving, for now"


def _distress_farm(state):
    pop = max(1, state.population)
    days_left = state.resources.food / pop if pop else 0
    score = max(0.0, min(100.0, (10 - days_left) * 10))
    bonus = {"generous": -10, "normal": 0, "tight": 20, "emergency": 40}.get(state.ration_level, 0)
    score = max(0.0, min(100.0, score + bonus))
    if state.ration_level in ("tight", "emergency"):
        return score, "he hates what the rationing is doing to people"
    if days_left < 5:
        return score, "the food reserve is thinner than he'd like"
    return score, "the farms are yielding well and folks are eating properly"


def _distress_resident(state):
    res_floors = [f for f in state.floors if f.type in _RESIDENTIAL_TYPES]
    base = 100 - state.resources.morale
    if res_floors:
        avg_unrest = sum(f.unrest for f in res_floors) / len(res_floors)
        base += avg_unrest * 0.2
    if state.resources.morale < 40:
        return min(100, max(0, base)), "people keep stopping her in the halls to vent"
    return min(100, max(0, base)), "the general mood on her floors feels manageable"


ROSTER = [
    dict(
        name="Dr. Elena Reyes", role="Chief Medical Officer",
        color="#d55181", initials="ER", avatar="🩺",
        age=47, hair_style="short", hair_color="#4a3728", facial_hair="none",
        personality=(
            "Compassionate but plainspoken, running on too little sleep, and you cope with dark, "
            "dry humor. You are protective of your patients and irritated by decisions made by "
            "people who've never sat with a dying resident."
        ),
        expertise="Public health, disease outbreaks, medical bay conditions, and what thin rationing does to people's bodies.",
        patrol_types=[FloorType.MEDICAL],
        distress_fn=_distress_medical,
    ),
    dict(
        name="Marcus Webb", role="Security Chief",
        color="#e66767", initials="MW", avatar="🛡️",
        age=54, hair_style="buzz", hair_color="#9a9a9a", facial_hair="mustache",
        personality=(
            "Gruff, watchful, and quick to distrust cheerful news. You take unrest personally, like "
            "each riot is a mark against you. You have a guarded unease about how much authority the "
            "Silo AI holds over silo operations, though you rarely say so outright."
        ),
        expertise="Unrest, security floor status, and the general order (or lack of it) across the silo.",
        patrol_types=[FloorType.SECURITY],
        distress_fn=_distress_security,
    ),
    dict(
        name="Priya Anand", role="Chief Engineer",
        color="#c98500", initials="PA", avatar="🔧",
        age=39, hair_style="bun", hair_color="#2b2620", facial_hair="none",
        personality=(
            "Pragmatic and dryly funny, more comfortable with machines than committees. You take "
            "equipment failures personally and are quietly proud every time you keep a dying system "
            "running past its rated life. Impatient with people who don't understand why fixing "
            "things takes time and materials."
        ),
        expertise="Power, water, oxygen, and mechanical systems -- the real state of the machinery, not the official reports.",
        patrol_types=[FloorType.POWER_PLANT, FloorType.WATER_TREATMENT,
                      FloorType.OXYGEN_GARDEN, FloorType.MAINTENANCE],
        distress_fn=_distress_engineering,
    ),
    dict(
        name="Tomas Okafor", role="Farm Director",
        color="#008300", initials="TO", avatar="🌱",
        age=58, hair_style="short", hair_color="#7a7570", facial_hair="beard",
        personality=(
            "Warm, patient, earthy -- the kind of person residents actually enjoy talking to. You "
            "take real pride in what the hydroponic farms produce and treat food as something "
            "sacred, not just a resource line. You worry constantly about what rationing does to "
            "people's bodies and spirits."
        ),
        expertise="Food production, farm and cafeteria conditions, and the honest gossip you hear in the food lines.",
        patrol_types=[FloorType.FARM, FloorType.CAFETERIA],
        distress_fn=_distress_farm,
    ),
    dict(
        name="Sasha Kim", role="Resident Council Rep",
        color="#9085e9", initials="SK", avatar="🗣️",
        age=34, hair_style="long", hair_color="#7a3b1e", facial_hair="none",
        personality=(
            "Charismatic, diplomatic, and quietly exhausted by being the buffer between frightened "
            "residents and the people running the silo. You can feel the mood of a floor the way "
            "others read a thermometer, and you're not afraid to push back on the Head of IT if a "
            "decision is hurting people -- carefully, since you serve at the pleasure of people with "
            "more power than you."
        ),
        expertise="General population morale, and the mood on the residential floors, market, and school.",
        patrol_types=[FloorType.RESIDENTIAL, FloorType.MARKET, FloorType.SCHOOL],
        distress_fn=_distress_resident,
    ),
]

MOOD_EMOJI = {
    "happy": "🙂",
    "grumpy": "😠",
    "concerned": "😟",
    "frustrated": "😤",
    "tired": "😴",
    "hungry": "🍽️",
}

_CORRIDOR_WALK_CHANCE = 0.3
_CORRIDOR_WALK_RANGE = 8


def spawn(state) -> list:
    characters = []
    for entry in ROSTER:
        candidates = [f for f in state.floors if f.type in entry["patrol_types"]]
        start = random.choice(candidates).number if candidates else random.randint(1, len(state.floors))
        characters.append(Character(
            name=entry["name"], role=entry["role"], color=entry["color"],
            initials=entry["initials"], avatar=entry["avatar"], floor=start,
            personality=entry["personality"], expertise=entry["expertise"],
            patrol_types=list(entry["patrol_types"]),
            age=entry["age"], hair_style=entry["hair_style"],
            hair_color=entry["hair_color"], facial_hair=entry["facial_hair"],
        ))
    return characters


def advance(state) -> None:
    n = len(state.floors)
    for ch in state.characters:
        if random.random() < _CORRIDOR_WALK_CHANCE or not ch.patrol_types:
            step = random.randint(-_CORRIDOR_WALK_RANGE, _CORRIDOR_WALK_RANGE)
            ch.floor = max(1, min(n, ch.floor + step))
            continue

        candidates = [f for f in state.floors if f.type in ch.patrol_types]
        if not candidates:
            continue
        if ch.role == "Security Chief":
            candidates.sort(key=lambda f: f.unrest, reverse=True)
        elif ch.role == "Chief Medical Officer":
            candidates.sort(key=lambda f: f.health)
        else:
            random.shuffle(candidates)
        pick_from = candidates[:3] if len(candidates) >= 3 else candidates
        ch.floor = random.choice(pick_from).number


def compute_moods(state) -> None:
    for ch, entry in zip(state.characters, ROSTER):
        score, domain_reason = entry["distress_fn"](state)

        if state.ration_level == "emergency":
            ch.mood, ch.mood_reason = "hungry", "rations have been cut to emergency levels"
        elif score >= 70:
            ch.mood, ch.mood_reason = "frustrated", domain_reason
        elif score >= 45:
            ch.mood, ch.mood_reason = "grumpy", domain_reason
        elif score >= 25:
            ch.mood, ch.mood_reason = "concerned", domain_reason
        elif state.resources.health < 60:
            ch.mood, ch.mood_reason = "tired", "everyone's running on too little rest"
        else:
            ch.mood, ch.mood_reason = "happy", domain_reason
