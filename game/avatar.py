"""Renders a small posable, *animated* SVG avatar for a character, driven
by two independent things: their CharacterReaction (see
game/character_ai.py) -- eyebrows, eyes, mouth, shoulders, arms, body
lean, legs -- which changes turn to turn, and their fixed appearance (see
game/models.py Character) -- hair style/color, facial hair, accent color
-- which doesn't. Mixing those up would mean a mood swing changes
someone's haircut, so the animated renderer takes both a `reaction` and
the `ch` they belong to, kept deliberately separate.

Coordinate system: viewBox "0 0 100 170", head at top, feet at bottom,
y grows downward. Built the same way as game/silo_view.py -- hand-coded
SVG, verified by rendering to PNG and looking at it, not just written and
assumed correct.

Hair/beard use one trick throughout: draw an oversized, offset shape
*behind* the head circle, then let the opaque head circle (drawn on top)
clip it down to just the sliver that should show -- a cap of hair peeking
above the hairline, or a beard peeking below the jaw -- without needing
real clipping paths.

Animation: every posable element carries a native SVG <animate> /
<animateTransform> (SMIL) that plays automatically on load, oscillating
between a neutral resting pose and the character's actual `reaction` a
couple of times before freezing on the reaction. This is genuine
attribute interpolation -- the browser smoothly tweens numbers between
keyframes -- not a toggle between two pre-rendered frames, which is why
this needs every animatable shape to stay *structurally* consistent
between poses (e.g. arm polylines always carry 3 points -- shoulder,
elbow-or-a-plain-midpoint, hand -- never 2 in one pose and 3 in another,
or the browser has nothing consistent to interpolate between). Being
plain SVG markup (no <script>), this renders fine through
st.markdown(..., unsafe_allow_html=True) -- no iframe/components.html
needed, unlike the TTS audio player elsewhere in this app.
"""

from game.character_ai import CharacterReaction

HEAD_CX, HEAD_CY, HEAD_R = 50.0, 26.0, 16.0
SHOULDER_Y_BASE = 52.0
SHOULDER_X_L, SHOULDER_X_R = 32.0, 68.0
HIP_Y = 100.0
HIP_X_L, HIP_X_R = 42.0, 58.0
GROUND_Y = 155.0

SKIN_COLOR = "#e0c9a8"
LINE_COLOR = "#0d1117"

# Animation timing: 6 keyframes (neutral/reaction alternating, ending on
# reaction) = 5 segments between them, evenly spaced across the duration.
_ANIM_DUR = "1.5s"
_ANIM_KEYTIMES = "0;0.2;0.4;0.6;0.8;1"


def _values_seq(neutral_val, reaction_val) -> str:
    return ";".join([str(neutral_val), str(reaction_val)] * 3)


def _animate(attr: str, neutral_val, reaction_val, extra: str = "") -> str:
    return (
        f'<animate attributeName="{attr}" values="{_values_seq(neutral_val, reaction_val)}" '
        f'keyTimes="{_ANIM_KEYTIMES}" dur="{_ANIM_DUR}" fill="freeze" {extra}/>'
    )


def _animate_transform(kind: str, neutral_val: str, reaction_val: str) -> str:
    return (
        f'<animateTransform attributeName="transform" type="{kind}" '
        f'values="{_values_seq(neutral_val, reaction_val)}" '
        f'keyTimes="{_ANIM_KEYTIMES}" dur="{_ANIM_DUR}" fill="freeze"/>'
    )


def _shoulder_y(reaction) -> float:
    return {"raise": 47.0, "lower": 58.0}.get(reaction.shoulder_movement, SHOULDER_Y_BASE)


def _body_angle(reaction) -> float:
    return {"lean_left": -15.0, "lean_right": 15.0}.get(reaction.body, 0.0)


# --- head features -----------------------------------------------------------

_BROW_BASE_L = {"x1": 37, "y1": 17, "x2": 46, "y2": 16}
_BROW_BASE_R = {"x1": 54, "y1": 16, "x2": 63, "y2": 17}


def _eyebrow_coords(eyebrow_reaction: str):
    l, r = dict(_BROW_BASE_L), dict(_BROW_BASE_R)
    if eyebrow_reaction == "raise_both":
        for seg in (l, r):
            seg["y1"] -= 3
            seg["y2"] -= 3
    elif eyebrow_reaction == "raise_left":
        l["y1"] -= 4
        l["y2"] -= 5
    elif eyebrow_reaction == "raise_right":
        r["y1"] -= 5
        r["y2"] -= 4
    return l, r


def _eyebrows_svg(reaction, neutral, hair_color: str) -> str:
    l0, r0 = _eyebrow_coords(neutral.eyebrow_reaction)
    l1, r1 = _eyebrow_coords(reaction.eyebrow_reaction)
    parts = []
    for s0, s1 in ((l0, l1), (r0, r1)):
        anims = _animate("y1", s0["y1"], s1["y1"]) + _animate("y2", s0["y2"], s1["y2"])
        parts.append(
            f'<line x1="{s0["x1"]}" y1="{s0["y1"]}" x2="{s0["x2"]}" y2="{s0["y2"]}" '
            f'stroke="{hair_color}" stroke-width="2" stroke-linecap="round">{anims}</line>'
        )
    return "".join(parts)


_EYE_OFFSETS = {
    "look_up": (0.0, -1.6), "look_down": (0.0, 1.6),
    "look_left": (-1.6, 0.0), "look_right": (1.6, 0.0),
    "look_straight": (0.0, 0.0),
}


def _eyes_svg(reaction, neutral) -> str:
    dx0, dy0 = _EYE_OFFSETS.get(neutral.eye_movement, (0.0, 0.0))
    dx1, dy1 = _EYE_OFFSETS.get(reaction.eye_movement, (0.0, 0.0))
    parts = []
    for base_cx in (43, 57):
        parts.append(f'<circle cx="{base_cx}" cy="24" r="3.2" fill="white" stroke="{LINE_COLOR}" stroke-width="0.8"/>')
        cx0, cy0 = base_cx + dx0, 24 + dy0
        cx1, cy1 = base_cx + dx1, 24 + dy1
        anims = _animate("cx", f"{cx0:.1f}", f"{cx1:.1f}") + _animate("cy", f"{cy0:.1f}", f"{cy1:.1f}")
        parts.append(f'<circle cx="{cx0:.1f}" cy="{cy0:.1f}" r="1.4" fill="{LINE_COLOR}">{anims}</circle>')
    return "".join(parts)


# Each entry: (y1, cx, cy, y2) for the path "M 44 {y1} Q {cx} {cy} 56 {y2}"
# -- x1=44/x2=56 held constant across every mood so the *whole* path stays
# structurally identical (same command sequence, same count of numbers)
# between any two moods, which is what lets the browser interpolate the
# `d` attribute smoothly instead of just snapping. "open" reuses the
# straight/neutral curve and gets its actual openness from a separate
# overlaid ellipse (a real oval can't be expressed in this same quadratic
# curve, so it isn't forced into it).
_MOUTH_POINTS = {
    "straight": (34, 50, 34, 34),
    "open": (34, 50, 34, 34),
    "smile": (33, 50, 40, 33),
    "frown": (37, 50, 29, 37),
    "big_smile": (32, 50, 45, 32),
    "raise_one_side": (34, 55, 31, 30),
}


def _mouth_svg(reaction, neutral) -> str:
    y1_0, cx0, cy0, y2_0 = _MOUTH_POINTS.get(neutral.mouth_movement, _MOUTH_POINTS["straight"])
    y1_1, cx1, cy1, y2_1 = _MOUTH_POINTS.get(reaction.mouth_movement, _MOUTH_POINTS["straight"])
    d0 = f"M 44 {y1_0} Q {cx0} {cy0} 56 {y2_0}"
    d1 = f"M 44 {y1_1} Q {cx1} {cy1} 56 {y2_1}"
    lip = f'<path d="{d0}" fill="none" stroke="{LINE_COLOR}" stroke-width="1.6" stroke-linecap="round">{_animate("d", d0, d1)}</path>'

    ry0 = 3.2 if neutral.mouth_movement == "open" else 0.05
    ry1 = 3.2 if reaction.mouth_movement == "open" else 0.05
    overlay = (
        f'<ellipse cx="50" cy="34" rx="3.6" ry="{ry0}" fill="{LINE_COLOR}">'
        f'{_animate("ry", ry0, ry1)}</ellipse>'
    )
    return lip + overlay


def _hair_under_svg(hair_style: str, hair_color: str) -> str:
    """The part of the hair that sits *behind* the head circle, clipped by
    it down to a cap around the top/sides. Static -- hairstyle doesn't
    animate, it's a fixed trait, not a reaction."""
    outline = f'stroke="{LINE_COLOR}" stroke-width="0.6"'
    if hair_style == "buzz":
        return f'<circle cx="{HEAD_CX}" cy="{HEAD_CY - 4}" r="{HEAD_R + 1.5}" fill="{hair_color}" {outline}/>'
    parts = [f'<circle cx="{HEAD_CX}" cy="{HEAD_CY - 5}" r="{HEAD_R + 2}" fill="{hair_color}" {outline}/>']
    if hair_style == "long":
        parts.append(f'<ellipse cx="32" cy="42" rx="6" ry="18" fill="{hair_color}" {outline}/>')
        parts.append(f'<ellipse cx="68" cy="42" rx="6" ry="18" fill="{hair_color}" {outline}/>')
    return "".join(parts)


def _hair_over_svg(hair_style: str, hair_color: str) -> str:
    if hair_style == "bun":
        return (
            f'<circle cx="{HEAD_CX}" cy="{HEAD_CY - HEAD_R - 4:.0f}" r="4.5" '
            f'fill="{hair_color}" stroke="{LINE_COLOR}" stroke-width="0.8"/>'
        )
    return ""


def _beard_svg(facial_hair: str, hair_color: str) -> str:
    if facial_hair != "beard":
        return ""
    return (
        f'<circle cx="{HEAD_CX}" cy="{HEAD_CY + 14:.0f}" r="{HEAD_R + 1}" fill="{hair_color}" '
        f'stroke="{LINE_COLOR}" stroke-width="0.6"/>'
    )


def _mustache_svg(facial_hair: str, hair_color: str) -> str:
    if facial_hair != "mustache":
        return ""
    return (
        f'<path d="M 43 31 Q 50 33.5 57 31" fill="none" '
        f'stroke="{hair_color}" stroke-width="3" stroke-linecap="round"/>'
    )


def _head_svg(reaction, neutral, ch) -> str:
    return (
        f"{_beard_svg(ch.facial_hair, ch.hair_color)}"
        f"{_hair_under_svg(ch.hair_style, ch.hair_color)}"
        f'<circle cx="{HEAD_CX}" cy="{HEAD_CY}" r="{HEAD_R}" fill="{SKIN_COLOR}" '
        f'stroke="{LINE_COLOR}" stroke-width="1.2"/>'
        f"{_eyebrows_svg(reaction, neutral, ch.hair_color)}{_eyes_svg(reaction, neutral)}{_mouth_svg(reaction, neutral)}"
        f"{_mustache_svg(ch.facial_hair, ch.hair_color)}"
        f"{_hair_over_svg(ch.hair_style, ch.hair_color)}"
    )


# --- torso + arms --------------------------------------------------------------

def _torso_svg(shoulder_y: float, color: str) -> str:
    return (
        f'<path d="M {SHOULDER_X_L} {shoulder_y:.0f} '
        f"L {SHOULDER_X_R} {shoulder_y:.0f} "
        f"L {HIP_X_R} {HIP_Y:.0f} L {HIP_X_L} {HIP_Y:.0f} Z\" "
        f'fill="{color}" stroke="{LINE_COLOR}" stroke-width="1.2"/>'
        f'<line x1="{HEAD_CX}" y1="{HEAD_CY + HEAD_R:.0f}" x2="{HEAD_CX}" y2="{shoulder_y + 6:.0f}" '
        f'stroke="{SKIN_COLOR}" stroke-width="7" stroke-linecap="round"/>'
    )


# Each entry: (left_elbow, left_hand, right_elbow, right_hand) as (dx, dy)
# offsets from that side's shoulder point -- each already independently
# correctly signed for its own side (negative dx = toward canvas-left), not
# a mirror-by-multiplication template (an earlier version double-flipped
# several poses that way -- caught by actually rendering and looking).
_ARM_OFFSETS = {
    "at_sides": (None, (5, 32), None, (-5, 32)),
    "raise_both": (None, (-10, -30), None, (10, -30)),
    "raise_left": (None, (-10, -30), None, (-5, 32)),
    "raise_right": (None, (5, 32), None, (10, -30)),
    "shrug": ((-16, 8), (-8, -2), (16, 8), (8, -2)),
    "wide_gesture": (None, (-32, -8), None, (32, -8)),
    "italian_hand_gesture": ((-14, 8), (-3, 20), (14, 8), (3, 20)),
}
_ARM_REST_L = (5, 32)
_ARM_REST_R = (-5, 32)


def _arm_offsets(arm_movement: str):
    offsets = _ARM_OFFSETS.get(arm_movement)
    if offsets is None:
        return None, _ARM_REST_L, None, _ARM_REST_R
    return offsets


def _arm_points(shoulder_x: float, shoulder_y: float, elbow_off, hand_off) -> str:
    hx, hy = shoulder_x + hand_off[0], shoulder_y + hand_off[1]
    if elbow_off is None:
        # Always emit 3 coordinate pairs, elbow-or-not, so this polyline's
        # "points" list has the same length in every pose -- required for
        # the browser to smoothly interpolate it rather than snap.
        ex, ey = (shoulder_x + hx) / 2, (shoulder_y + hy) / 2
    else:
        ex, ey = shoulder_x + elbow_off[0], shoulder_y + elbow_off[1]
    return f"{shoulder_x:.1f},{shoulder_y:.1f} {ex:.1f},{ey:.1f} {hx:.1f},{hy:.1f}"


def _one_arm(shoulder_x: float, shoulder_y: float, elbow0, hand0, elbow1, hand1) -> str:
    points0 = _arm_points(shoulder_x, shoulder_y, elbow0, hand0)
    points1 = _arm_points(shoulder_x, shoulder_y, elbow1, hand1)
    return (
        f'<polyline points="{points0}" fill="none" stroke="{SKIN_COLOR}" stroke-width="6" '
        f'stroke-linecap="round" stroke-linejoin="round">{_animate("points", points0, points1)}</polyline>'
    )


def _arms_svg(reaction, neutral, shoulder_y: float) -> str:
    l_elbow0, l_hand0, r_elbow0, r_hand0 = _arm_offsets(neutral.arm_movement)
    l_elbow1, l_hand1, r_elbow1, r_hand1 = _arm_offsets(reaction.arm_movement)
    left = _one_arm(SHOULDER_X_L, shoulder_y, l_elbow0, l_hand0, l_elbow1, l_hand1)
    right = _one_arm(SHOULDER_X_R, shoulder_y, r_elbow0, r_hand0, r_elbow1, r_hand1)
    return left + right


# --- legs ----------------------------------------------------------------------

# Each entry: (left_knee, left_foot, right_knee, right_foot) as absolute (x, y).
_LEG_POSES = {
    "stand": ((41, 127), (40, 155), (59, 127), (60, 155)),
    "step_left": ((35, 125), (28, 152), (59, 127), (60, 155)),
    "step_right": ((41, 127), (40, 155), (65, 125), (72, 152)),
    "walk": ((38, 120), (30, 148), (62, 130), (66, 158)),
    "jump": ((38, 116), (36, 130), (62, 116), (64, 130)),
}


def _leg_points(hip_x: float, knee, foot) -> str:
    return f"{hip_x:.0f},{HIP_Y:.0f} {knee[0]},{knee[1]} {foot[0]},{foot[1]}"


def _legs_svg(reaction, neutral) -> str:
    knee_l0, foot_l0, knee_r0, foot_r0 = _LEG_POSES.get(neutral.legs, _LEG_POSES["stand"])
    knee_l1, foot_l1, knee_r1, foot_r1 = _LEG_POSES.get(reaction.legs, _LEG_POSES["stand"])
    parts = [
        f'<line x1="0" y1="{GROUND_Y:.0f}" x2="100" y2="{GROUND_Y:.0f}" '
        f'stroke="#30363d" stroke-width="1" stroke-dasharray="2,2"/>'
    ]
    for hip_x, k0, f0, k1, f1 in (
        (HIP_X_L, knee_l0, foot_l0, knee_l1, foot_l1),
        (HIP_X_R, knee_r0, foot_r0, knee_r1, foot_r1),
    ):
        points0 = _leg_points(hip_x, k0, f0)
        points1 = _leg_points(hip_x, k1, f1)
        parts.append(
            f'<polyline points="{points0}" fill="none" stroke="{LINE_COLOR}" stroke-width="6" '
            f'stroke-linecap="round" stroke-linejoin="round">{_animate("points", points0, points1)}</polyline>'
        )
    return "".join(parts)


# --- public API ------------------------------------------------------------------

def _build_svg(reaction, neutral, ch, size: int) -> str:
    """Shared by both entry points below. Every <animate> here oscillates
    between `neutral`'s value and `reaction`'s value -- pass the same
    object for both and every animation collapses to a constant (the
    *base* attribute value, which a non-SMIL-aware renderer like
    rsvg-convert shows as-is), giving a correct static single-pose render
    for free rather than needing a separate non-animated code path."""
    shoulder_y = _shoulder_y(reaction)  # shoulder height itself doesn't animate; reach does
    body_angle0, body_angle1 = _body_angle(neutral), _body_angle(reaction)
    body_transform_attr = f"rotate({body_angle0} 50 {HIP_Y:.0f})"
    parts = [
        f'<svg viewBox="0 0 100 170" width="{size}" xmlns="http://www.w3.org/2000/svg">',
        _legs_svg(reaction, neutral),
        f'<g transform="{body_transform_attr}">',
        _animate_transform("rotate", f"{body_angle0} 50 {HIP_Y:.0f}", f"{body_angle1} 50 {HIP_Y:.0f}"),
        _torso_svg(shoulder_y, ch.color),
        _arms_svg(reaction, neutral, shoulder_y),
        _head_svg(reaction, neutral, ch),
        "</g>",
        "</svg>",
    ]
    return "".join(parts)


def render_animated(reaction, ch, size: int = 150) -> str:
    """Returns a self-contained <svg> string, every posable part carrying
    an <animate>/<animateTransform> from a neutral resting pose to
    `reaction`. `ch`'s fixed appearance -- accent color, hair, facial hair
    -- is layered on top, unanimated.

    Note this alone does NOT reliably autoplay when injected via
    st.markdown(..., unsafe_allow_html=True): SMIL's default begin timing
    is tied to the SVG's owning document actually *loading*, and
    dangerouslySetInnerHTML-style DOM insertion into an already-loaded
    page fires no load event for that content -- so the animation can
    just sit at frame 0 forever. Use render_animated_html() below (embeds
    via st.components.v1.html, a real iframe with its own load event, and
    also force-starts every animation explicitly as a second safety net)
    unless you specifically want the bare, unwrapped SVG."""
    return _build_svg(reaction, CharacterReaction(text=""), ch, size)


def render_animated_html(reaction, ch, size: int = 150):
    """Returns (html, height) for st.components.v1.html(). Wraps
    render_animated()'s SVG in a real HTML document (so SMIL's load-tied
    default start timing has an actual load event to trigger on) and,
    belt-and-suspenders, explicitly calls .beginElement() on every
    animation node once the DOM is ready -- the standard, documented way
    to force-(re)start SMIL programmatically, covering any browser/case
    where load-event timing alone isn't enough."""
    svg = render_animated(reaction, ch, size=size)
    height = int(size * 1.7) + 10
    html = f"""
    <div style="width:{size}px; height:{height}px;">{svg}</div>
    <script>
    (function() {{
        var svg = document.querySelector("svg");
        if (!svg) return;
        var anims = svg.querySelectorAll("animate, animateTransform");
        anims.forEach(function(a) {{
            try {{ a.beginElement(); }} catch (e) {{}}
        }});
    }})();
    </script>
    """
    return html, height


def render(reaction, ch, size: int = 150) -> str:
    """A single static pose, no animation -- for anything that renders to
    a non-SMIL context (a quick debug/QA script rasterizing with
    rsvg-convert, for instance) where an animated version would only ever
    show its starting (neutral) frame."""
    return _build_svg(reaction, reaction, ch, size)
