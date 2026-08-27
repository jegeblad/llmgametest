"""Renders the silo as an inline SVG architectural cross-section: a central
core (stairwell + elevator shaft) running the full height, with a hallway
and a room band extending out to each side on every floor, color-coded by
functional zone. Room width scales with that floor's current population
(so a floor a cull hits visibly shrinks), set against a rock/earth band on
both sides -- narrower floors simply show more rock, which is also where
mine shafts from the Power Plant floors (fuel extraction) tunnel outward.
Condition/unrest trouble is a separate status-color outline, and named
personnel appear as markers along the right edge.

Zone fill uses 3 categorical hues (validated colorblind-safe under an
all-pairs check, appropriate since floor types are interleaved and any two
zone colors can end up adjacent) -- deliberately not one hue per floor type,
since at 4px/row with 200 rows and 12 raw types, no palette holds up under
scrutiny. Exact per-floor type is always available via hover tooltip and the
sortable data table; the diagram itself is a gestalt/overview tool.
"""

from game.models import FloorType

# Categorical zone fill -- 3 slots from the validated palette (dark-mode
# steps), passing CVD/normal-vision all-pairs checks against our #0d1117
# surface. Deliberately not reordered/cycled beyond this set.
ZONE_COLORS = {
    "residential": "#3987e5",   # slot 1 blue
    "systems": "#d95926",       # slot 2 orange
    "public_safety": "#199e70", # slot 3 aqua
}

ZONE_LABELS = {
    "residential": "Residential",
    "systems": "Systems (Farm / Power / Water / O2 / Maintenance / IT)",
    "public_safety": "Public & Safety (Cafeteria / Market / School / Medical / Security)",
}

_TYPE_TO_ZONE = {
    FloorType.RESIDENTIAL: "residential",
    FloorType.FARM: "systems",
    FloorType.POWER_PLANT: "systems",
    FloorType.WATER_TREATMENT: "systems",
    FloorType.OXYGEN_GARDEN: "systems",
    FloorType.MAINTENANCE: "systems",
    FloorType.IT_DEPARTMENT: "systems",
    FloorType.CAFETERIA: "public_safety",
    FloorType.MARKET: "public_safety",
    FloorType.SCHOOL: "public_safety",
    FloorType.MEDICAL: "public_safety",
    FloorType.SECURITY: "public_safety",
    FloorType.STORAGE: "systems",
}

# Reserved status palette (dark-mode steps) -- never reused for zone fill,
# always shipped as an outline + the tooltip's exact numbers (never color
# alone).
STATUS_WARNING = "#fab219"
STATUS_CRITICAL = "#d03b3b"

CORRIDOR_COLOR = "#30363d"   # hallway stub, distinct from room, shaft, and rock fills
SHAFT_COLOR = "#161b22"
RAIL_COLOR = "#8b949e"
ROCK_BASE = "#21262d"
ROCK_LINE = "#30363d"
MINE_COLOR = "#c9975a"       # ore/rock brown -- decorative only, not a data channel

ROW_HEIGHT = 4
MIN_ROOM_WIDTH = 30
MAX_ROOM_WIDTH = 100
ROCK_MARGIN = 34             # how far rock extends beyond the widest possible room
CORRIDOR_WIDTH = 7
SHAFT_WIDTH = 34
LEFT_LABEL_MARGIN = 28       # room for floor-number ticks, left of the rock band
TOP_MARGIN = 22
RIGHT_MARGIN = 170           # room for character badges/labels
CAP_HEIGHT = 10
BEDROCK_HEIGHT = 14
MINE_TUNNEL_LEN = ROCK_MARGIN - 8


def _zone_color(ftype: FloorType) -> str:
    zone = _TYPE_TO_ZONE.get(ftype, "systems")
    return ZONE_COLORS[zone]


def _status_stroke(floor) -> str:
    if floor.condition < 30 or floor.unrest >= 70:
        return STATUS_CRITICAL
    if floor.condition < 60 or floor.unrest >= 40:
        return STATUS_WARNING
    return ""


def _room_width(pop, min_pop, max_pop) -> float:
    if max_pop <= min_pop:
        return (MIN_ROOM_WIDTH + MAX_ROOM_WIDTH) / 2
    ratio = (pop - min_pop) / (max_pop - min_pop)
    return MIN_ROOM_WIDTH + ratio * (MAX_ROOM_WIDTH - MIN_ROOM_WIDTH)


def render(state) -> str:
    n = len(state.floors)
    shaft_top = TOP_MARGIN
    shaft_bottom = TOP_MARGIN + n * ROW_HEIGHT

    left_area_width = ROCK_MARGIN + MAX_ROOM_WIDTH
    right_area_width = MAX_ROOM_WIDTH + ROCK_MARGIN

    left_area_x = LEFT_LABEL_MARGIN
    corridor_l_x = left_area_x + left_area_width
    shaft_x = corridor_l_x + CORRIDOR_WIDTH
    corridor_r_x = shaft_x + SHAFT_WIDTH
    right_area_x = corridor_r_x + CORRIDOR_WIDTH
    shell_right_x = right_area_x + right_area_width

    total_height = shaft_bottom + CAP_HEIGHT + BEDROCK_HEIGHT
    total_width = shell_right_x + RIGHT_MARGIN

    pops = [f.population for f in state.floors]
    min_pop, max_pop = min(pops), max(pops)

    parts = [
        f'<svg viewBox="0 0 {total_width} {total_height}" width="100%" '
        f'xmlns="http://www.w3.org/2000/svg" font-family="monospace">',
        "<defs>",
        '<pattern id="rockHatch" width="8" height="8" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">',
        f'<rect width="8" height="8" fill="{ROCK_BASE}"/>',
        f'<line x1="0" y1="0" x2="0" y2="8" stroke="{ROCK_LINE}" stroke-width="2.5"/>',
        "</pattern>",
        "</defs>",
        f'<rect x="0" y="0" width="{total_width}" height="{total_height}" fill="#0d1117"/>',
    ]

    # roof cap
    parts.append(
        f'<rect x="{left_area_x - 2}" y="{TOP_MARGIN - CAP_HEIGHT}" width="{shell_right_x - left_area_x + 4}" '
        f'height="{CAP_HEIGHT}" rx="2" fill="#21262d" stroke="{RAIL_COLOR}" stroke-width="1"/>'
    )

    # rock/earth bands flanking the structure -- rooms narrower than the max
    # simply leave more of this visible, which is also where mine tunnels end
    for x, w in ((left_area_x, left_area_width), (right_area_x, right_area_width)):
        parts.append(
            f'<rect x="{x}" y="{shaft_top}" width="{w}" height="{shaft_bottom - shaft_top}" '
            f'fill="url(#rockHatch)" stroke="{RAIL_COLOR}" stroke-width="1"><title>Surrounding rock</title></rect>'
        )

    # per-floor bands: room (variable width) / corridor / (shaft) / corridor / room
    mine_floors = [f for f in state.floors if f.type == FloorType.POWER_PLANT]
    mine_side = {f.number: (i % 2 == 0) for i, f in enumerate(mine_floors)}  # alternate by order, not floor parity
    mine_parts = []
    for f in state.floors:
        y = TOP_MARGIN + (f.number - 1) * ROW_HEIGHT
        mid_y = y + ROW_HEIGHT / 2
        w = _room_width(f.population, min_pop, max_pop)
        fill = _zone_color(f.type)
        stroke = _status_stroke(f)
        stroke_attr = f' stroke="{stroke}" stroke-width="1"' if stroke else ""
        title = _escape(
            f"Floor {f.number} — {f.type.value}\n"
            f"Pop {f.population} · Condition {f.condition:.0f}% · Unrest {f.unrest:.0f} · {f.status}"
        )

        room_l_x = corridor_l_x - w
        parts.append(
            f'<rect x="{room_l_x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{ROW_HEIGHT}" '
            f'fill="{fill}"{stroke_attr}><title>{title}</title></rect>'
        )
        parts.append(
            f'<rect x="{corridor_l_x}" y="{y:.1f}" width="{CORRIDOR_WIDTH}" height="{ROW_HEIGHT}" '
            f'fill="{CORRIDOR_COLOR}"><title>{title}</title></rect>'
        )
        parts.append(
            f'<rect x="{corridor_r_x}" y="{y:.1f}" width="{CORRIDOR_WIDTH}" height="{ROW_HEIGHT}" '
            f'fill="{CORRIDOR_COLOR}"><title>{title}</title></rect>'
        )
        parts.append(
            f'<rect x="{right_area_x}" y="{y:.1f}" width="{w:.1f}" height="{ROW_HEIGHT}" '
            f'fill="{fill}"{stroke_attr}><title>{title}</title></rect>'
        )

        if f.number in mine_side:
            on_left = mine_side[f.number]
            if on_left:
                x0, y0 = room_l_x, mid_y
                x1, y1 = x0 - MINE_TUNNEL_LEN, mid_y - 6
            else:
                x0, y0 = right_area_x + w, mid_y
                x1, y1 = x0 + MINE_TUNNEL_LEN, mid_y + 6
            mine_title = _escape(f"Mine shaft — fuel extraction tunnel (Floor {f.number})")
            mine_parts.append(
                f'<line x1="{x0:.1f}" y1="{y0:.1f}" x2="{x1:.1f}" y2="{y1:.1f}" '
                f'stroke="{MINE_COLOR}" stroke-width="1.6" stroke-linecap="round"><title>{mine_title}</title></line>'
            )
            mine_parts.append(
                f'<circle cx="{x1:.1f}" cy="{y1:.1f}" r="2" fill="{MINE_COLOR}"><title>{mine_title}</title></circle>'
            )

    parts.extend(mine_parts)

    # floor number ticks every 20 floors
    for fn in range(1, n + 1, 20):
        y = TOP_MARGIN + (fn - 1) * ROW_HEIGHT
        parts.append(
            f'<text x="{left_area_x - 6}" y="{y + 3:.1f}" fill="{RAIL_COLOR}" font-size="8" text-anchor="end">{fn}</text>'
        )

    # --- central core: stairwell (left lane) + elevator shaft (right lane) ---
    parts.append(
        f'<rect x="{shaft_x}" y="{shaft_top}" width="{SHAFT_WIDTH}" height="{shaft_bottom - shaft_top}" '
        f'fill="{SHAFT_COLOR}" stroke="{RAIL_COLOR}" stroke-width="1.2"><title>Central core — stairwell and elevator</title></rect>'
    )
    parts.append(
        f'<line x1="{shaft_x + SHAFT_WIDTH / 2:.1f}" y1="{shaft_top}" x2="{shaft_x + SHAFT_WIDTH / 2:.1f}" '
        f'y2="{shaft_bottom}" stroke="{RAIL_COLOR}" stroke-width="0.6" opacity="0.5"/>'
    )

    # stairwell zigzag (left lane)
    stair_left = shaft_x + 4
    stair_right = shaft_x + SHAFT_WIDTH / 2 - 3
    switchbacks = max(4, n // 7)
    step = (shaft_bottom - shaft_top) / switchbacks
    points = []
    for i in range(switchbacks + 1):
        y = shaft_top + i * step
        x = stair_left if i % 2 == 0 else stair_right
        points.append(f"{x:.1f},{y:.1f}")
    parts.append(
        f'<polyline points="{" ".join(points)}" fill="none" stroke="{RAIL_COLOR}" '
        f'stroke-width="1" opacity="0.8"><title>Stairwell</title></polyline>'
    )

    # elevator shaft (right lane): guide rails + a car positioned by cycle number
    elev_left = shaft_x + SHAFT_WIDTH / 2 + 3
    elev_right = shaft_x + SHAFT_WIDTH - 4
    parts.append(
        f'<line x1="{elev_left:.1f}" y1="{shaft_top}" x2="{elev_left:.1f}" y2="{shaft_bottom}" '
        f'stroke="{RAIL_COLOR}" stroke-width="0.6" opacity="0.6"/>'
    )
    parts.append(
        f'<line x1="{elev_right:.1f}" y1="{shaft_top}" x2="{elev_right:.1f}" y2="{shaft_bottom}" '
        f'stroke="{RAIL_COLOR}" stroke-width="0.6" opacity="0.6"/>'
    )
    elevator_floor = 1 + (state.cycle * 37) % n
    elev_y = TOP_MARGIN + (elevator_floor - 1) * ROW_HEIGHT
    parts.append(
        f'<rect x="{elev_left + 1:.1f}" y="{elev_y - 5:.1f}" width="{elev_right - elev_left - 2:.1f}" '
        f'height="10" rx="1" fill="#58a6ff" stroke="#0d1117" stroke-width="1">'
        f'<title>{_escape(f"Elevator — near Floor {elevator_floor}")}</title></rect>'
    )

    # bedrock footer
    bedrock_y = shaft_bottom + 2
    parts.append(
        f'<rect x="{left_area_x - 2}" y="{bedrock_y}" width="{shell_right_x - left_area_x + 4}" '
        f'height="{BEDROCK_HEIGHT}" fill="url(#rockHatch)" stroke="{RAIL_COLOR}" stroke-width="1"/>'
    )
    parts.append(
        f'<text x="{(left_area_x + shell_right_x) / 2:.1f}" y="{bedrock_y + BEDROCK_HEIGHT / 2 + 3:.1f}" '
        f'fill="{RAIL_COLOR}" font-size="7" text-anchor="middle" opacity="0.9">BEDROCK</text>'
    )

    # character markers, offset to avoid label collisions
    used_label_y = []
    for ch in state.characters:
        y = TOP_MARGIN + (ch.floor - 1) * ROW_HEIGHT + ROW_HEIGHT / 2
        label_y = y
        while any(abs(label_y - uy) < 15 for uy in used_label_y):
            label_y += 15
        used_label_y.append(label_y)

        badge_x = shell_right_x + 16
        parts.append(
            f'<line x1="{shell_right_x}" y1="{y:.1f}" x2="{badge_x - 8}" y2="{label_y:.1f}" '
            f'stroke="{ch.color}" stroke-width="1" opacity="0.6"/>'
        )
        parts.append(
            f'<circle cx="{badge_x}" cy="{label_y:.1f}" r="7.5" fill="{ch.color}" '
            f'stroke="#0d1117" stroke-width="1.5"><title>{_escape(f"{ch.name} — {ch.role} (Floor {ch.floor})")}</title></circle>'
        )
        parts.append(
            f'<text x="{badge_x}" y="{label_y + 2.8:.1f}" fill="#0d1117" font-size="7.5" '
            f'text-anchor="middle" font-weight="bold">{ch.initials}</text>'
        )
        parts.append(
            f'<text x="{badge_x + 12}" y="{label_y + 3:.1f}" fill="#c9d1d9" font-size="9">'
            f'{_escape(ch.name.split()[-1])} · F{ch.floor}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


def _escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")
