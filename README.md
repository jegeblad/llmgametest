# Silo

A Streamlit web app: you are the Head of IT inside a sealed underground silo
of ~10,000 people spread across 200 floors. The outside world is gone. Food,
water, oxygen, fuel, and power are all finite and must be actively managed.
A Gemini-powered "Silo AI" has full sensor access to the silo's status and
advises you on request — but only you can issue directives. It also
administers the Continuity Protocol: a fail-safe that arms if stability or
morale stay critical too long, and executes a population "cull" itself if
you don't resolve it in time. Repeated culls end the game outright. It is
never a strategy, only a threat to avoid.

## Setup

```
pip install -r requirements.txt
cp .env.example .env   # then edit .env and add your GEMINI_API_KEY
streamlit run app.py
```

This starts a local web server and opens the game in your browser (default
`http://localhost:8501`).

No API key? The game still runs — the AI advisor falls back to a raw
telemetry summary instead of live Gemini responses, and voice is simply
unavailable.

### Local models (Ollama)

The Silo AI and character chats can run on a local model instead of Gemini
— useful for playing offline or without API cost. Swapping is one env var,
not a code change: both `game/ai_advisor.py` and `game/character_ai.py` go
through `game/llm_client.py`, a small facade that picks between
`game/gemini_client.py` (default) and `game/ollama_client.py` based on
`LLM_BACKEND`.

```
brew install --cask ollama      # or see https://ollama.com/download
ollama serve                    # start the local server (leave running)
ollama pull gpt-oss:20b         # ~13GB, one-time
LLM_BACKEND=ollama streamlit run app.py
```

Defaults to `gpt-oss:20b` (OpenAI's open-weight model, sized to fit
comfortably in 16GB of RAM/VRAM with native structured-output support) —
override with `OLLAMA_MODEL`, or point at a non-default server with
`OLLAMA_HOST`. Swap back anytime by unsetting `LLM_BACKEND` (or setting it
to `gemini`) — no code changes either way.

Validated live, not just wired up and hoped for: the same enum-constrained
JSON schema Gemini fills for `CharacterReaction` (`game/character_ai.py`)
round-trips correctly through Ollama's `format` parameter, and a calm
question versus a sudden-riot question produced genuinely different poses
(mouth `smile` → `frown`, shoulders `lower` → `raise`) at ~5-7s per
response on a M-series Mac. Voice (below) is unaffected either way and
always uses Gemini TTS regardless of `LLM_BACKEND`.

### Voice

The Silo AI and all five characters can be read aloud, via Gemini's TTS
model (`gemini-2.5-flash-preview-tts` by default — override with
`GEMINI_TTS_MODEL`), reusing your existing `GEMINI_API_KEY`. Each speaker
has a distinct prebuilt Gemini voice — the Silo AI uses "Charon", chosen by
actually measuring pitch across 20 candidate voices rather than guessing
from names (it came out deepest, ~103Hz median). It also always speaks
fast, blunt, deep, and flat — "rapid-fire... deep, flat, mechanical
monotone, blunt and unfriendly" — which are real, measured effects, not
just hopeful adjectives: the "rapid-fire" phrasing cuts clip duration by
~35% (reproduced across repeated runs of the same line), and the deep/flat
framing measurably drops median pitch and cuts pitch variance versus no
style at all (flatter intonation reads as synthetic/robotic). Characters'
delivery shifts with their current mood instead (e.g. "tired, noticeably
slower than usual"), via a style instruction Gemini TTS treats as delivery
guidance rather than text to actually speak — also confirmed empirically.
Toggle it off
anytime with the "🔊 Read responses aloud" checkbox in the sidebar. Each
reply triggers one real API call for audio generation on top of the text
reply, so expect a couple of extra seconds and a little extra API cost per
message.

### API usage & cost tracking

Every Gemini call (Silo AI, character chat, TTS) is logged to
`usage_log.jsonl` at the project root — one JSON line per call, with a
timestamp, model, speaker, and input/output token counts. The **💳 API
usage** panel in the sidebar sums that file into an all-time total (not
just the current browser session) and converts it to an estimated cost at
the rates in `game/usage.py::PRICING`. It's an estimate from real logged
token counts, not a guess — but Google's own billing dashboard is always
the authority. The log survives "Restart Silo" and app/server restarts;
delete `usage_log.jsonl` to reset the counter, or update `PRICING` if
Gemini's rates change.

For a terminal summary without launching the app, run:

```
python3 report_usage.py
```

## Playing

The dashboard (resources, morale, stability, health, Continuity Protocol
status, this cycle's events) spans the top. Below that the page splits in
two: the **Silo AI chat** in the middle, the **Silo Cross-Section** diagram
on the right. A sortable/filterable floor data table sits at the bottom.
The **IT Console** in the sidebar (far left) is how you issue directives:

- **Advance Cycle** — runs the simulation forward one day. Local-only (no
  API call), so it's instant.
- **Real-Time Mode** — a checkbox that auto-advances cycles on a timer
  instead of waiting for clicks (interval 1–30s, your choice). See below.
- **Maintenance** — dispatch a repair crew to a floor.
- **Security** — deploy security to reduce unrest on a floor.
- **Rationing** — generous / normal / tight / emergency.
- **Power Routing** — balanced / life_support / residential / security.
- **Broadcast** — reassure / honest / warn.
- **Lockdown** — engage or lift a floor lockdown.

Actions apply immediately, without needing to advance the cycle. The Silo
AI is **not** consulted automatically each cycle — advancing time is pure
local simulation, free and instant. Talk to it any time via the chat box in
the middle column, or click "📋 Request Status Report" for the same kind of
situation report it used to give automatically. It answers naturally in
character, not just with status dumps.

### Real-Time Mode

Turn on "▶ Auto-advance cycles" in the sidebar and the silo runs itself,
ticking forward on the interval you pick, no clicking required — good for
watching a long game play out, or leaving it running while you decide what
to do. Since the AI is never called automatically (see above), a tick is
just local math and stays fast regardless of interval. The Silo AI and
characters keep working normally throughout — ask them anything, whenever
you want, mid-tick or not.

Implementation note, in case you're reading the code: the naive version of
this (`st.fragment(run_every=...)` calling `st.rerun()` on each tick) looks
right but isn't — `st.rerun()` forces the whole script to re-run immediately,
which reaches the fragment's call site synchronously rather than waiting for
the next timer, so it cascades into a tight loop with no real delay (this
shipped once and was caught live: 24 cycles fired almost instantly instead
of one every 5 seconds). The fix is a wall-clock gate in `render_realtime_tick`
that only actually advances once the configured interval has truly elapsed,
regardless of how often the function gets invoked.

### Silo Cross-Section

A scrollable SVG architectural cross-section: a central core (stairwell with
a switchback zigzag, and an elevator shaft with a car that moves cycle to
cycle) runs the full height, with a hallway and a room band extending out
to each side on every floor, colored by functional zone (Residential /
Systems / Public & Safety). Room width scales with that floor's current
population, so bigger floors visibly bulge outward and a floor a cull hits
noticeably shrinks on the next render; the space between a narrower room
and the surrounding rock is filled with a hatched earth texture. A few of
those rock bands have mine shafts tunneling out from the Power Plant floors
(fuel extraction) — small brown tunnels ending in a shaft face. Condition
and unrest trouble get their own separate colored outline (yellow =
degraded/unrest, red = critical) — hover any row for its exact numbers.
Five named personnel wander the silo and appear as colored markers with
leader lines to their current floor:

- **Dr. Elena Reyes** — Chief Medical Officer (drawn to the sickest Medical floors)
- **Marcus Webb** — Security Chief (drawn to the most unrest)
- **Priya Anand** — Chief Engineer (Power / Water / Oxygen / Maintenance)
- **Tomas Okafor** — Farm Director (Farms / Cafeteria)
- **Sasha Kim** — Resident Council Rep (Residential / Market / School)

They move each cycle — mostly toward floors relevant to their role, with an
occasional corridor walk to a nearby floor. Position is flavor; they aren't
simulated individually and are untouched by famine, riots, or the Continuity
Protocol.

### Talking to personnel

Each of the five has their own tab next to Silo AI in the middle column, with
their own persistent chat history and a mood badge (🙂 happy, 😠 grumpy, 😟
concerned, 😤 frustrated, 😴 tired, 🍽️ hungry) that updates every cycle from
a distress score scoped to *their* domain — Elena's mood tracks public health
and medical floor conditions, Marcus's tracks stability and unrest on his
patrol floors, Priya's tracks power output and systems condition, Tomas's
tracks food reserves and rationing, Sasha's tracks morale and residential
unrest. Emergency rations make everyone hungry regardless of domain.

Unlike the Silo AI, they do **not** have silo-wide sensor access — each is an
independently-scoped Gemini chat session that only knows what it would
plausibly know from its own patrol floors, and will honestly say "that's not
my department" (while maybe offering a rumor anyway) if asked about something
outside their expertise. Their mood colors their tone each time you talk to
them, not just what they say.

Every reply is structured, not just free text: Gemini's schema-constrained
JSON output (`game/character_ai.py::CharacterReaction`) returns dialogue
plus a physical reaction — eyebrows, eyes, mouth, shoulders, arms
("at_sides" is the relaxed default; "shrug" is a real gesture of doubt or
dismissiveness, reserved for when they mean it, not a generic filler —
confirmed live that calm/routine questions now get "at_sides" rather than
defaulting to a shrug), body lean, legs. Plus a "🎭 ..." stage-direction
caption (e.g. "eyebrows raised · big smile · gesturing broadly").

This drives a small **animated** SVG avatar (`game/avatar.py`) shown next
to each character's chat, colored with their own accent color, that plays
on every render: starts at a neutral resting pose and smoothly animates —
genuine native SVG attribute interpolation (SMIL `<animate>` /
`<animateTransform>`), not a toggle between two pre-rendered frames — back
and forth to their latest reaction a couple of times before freezing on
it. Every animatable shape (arm/leg polylines, the mouth curve) is kept
structurally identical between poses specifically so the browser has
something consistent to interpolate rather than snap between. It's plain
SVG markup with no `<script>`, so it renders through a normal
`st.markdown(..., unsafe_allow_html=True)` — no iframe needed.

Each character also has a fixed appearance, independent of mood: an age,
hair style/color, and facial hair (`game/models.py` Character /
`game/characters.py` ROSTER) — Elena (47, short dark hair), Marcus (54,
buzz cut, grey, mustache), Priya (39, dark hair in a bun), Tomas (58, grey
hair and full beard), Sasha (34, long auburn hair). Hair/beard rendering
reuses one trick throughout: draw an oversized, offset shape *behind* the
head circle and let the opaque head (drawn on top) clip it down to just
the sliver that should show.

Validated live before shipping, not just written and hoped for: good
news, bad news, and sudden alarm each produced genuinely different,
appropriate poses (and appropriately different avatar renders) rather
than a repeated neutral default; a real arm-mirroring bug (one pose's
gesture landing on the wrong side of the body, hidden behind the torso)
and a real `UnboundLocalError` (a local variable shadowing the `avatar`
module import) were both caught by actually running the app, not by
reading the code.

## Losing

Morale and stability drain on their own every cycle (confinement takes a
toll, whether or not you're paying attention) — leave the silo unmanaged
and the Continuity Protocol arms in roughly two weeks, with termination not
far behind. Only active intervention outpaces it: **broadcast** counters
the morale drain, **security** counters the stability drain. A silo you
never touch is a silo on a clock; one you actively run can be sustained
indefinitely.

The silo fails if population collapses through attrition, or if the
Continuity Protocol runs its course: armed when stability drops below 40 or
morale below 35, it gives you a few cycles to recover both above ~50/45
before it acts. A cull relieves stability but costs morale and health — it
tends to make the underlying problem worse, not better — and three of them
trigger full termination. Watch food/water/oxygen days-of-reserve on the
dashboard, and the AI's warnings — it will call out impending famine,
oxygen shortfalls, riot risk, and the Protocol's own countdown before any
of it hits. A "Restart Silo" button appears on the failure screen.

## Structure

```
app.py                 Streamlit UI: dashboard, IT console, AI chat, game loop
game/models.py          Floor, Character, Resources, SiloState dataclasses
game/constants.py       Tunable simulation numbers (floor counts, yields, etc.)
game/simulation.py      Per-cycle production/consumption of food/water/O2/power
game/events.py          Random events (equipment failure, outbreaks, riots...)
game/actions.py         Player directives (repair, security, rationing, etc.)
game/failsafe.py        Continuity Protocol: arm / cull / terminate escalation
game/ai_advisor.py      Silo AI: chat session (via llm_client), prompt building, offline fallback
game/llm_client.py      Backend facade: picks gemini_client or ollama_client via LLM_BACKEND
game/gemini_client.py   Gemini client/chat factory (cloud backend, default)
game/ollama_client.py   Ollama client/chat factory (local backend, LLM_BACKEND=ollama)
game/character_ai.py    Per-character chat sessions: domain-scoped, mood-colored, structured reactions
game/avatar.py          Animated SVG avatar rig (SMIL), posed by CharacterReaction + fixed appearance
game/characters.py      Named personnel roster, per-cycle movement, and mood engine
game/silo_view.py       SVG cross-section renderer (zones, status, personnel)
game/speech.py          Gemini TTS: per-speaker voice, mood-driven style, sidebar toggle
game/usage.py           All-time token/cost tracking, logged to usage_log.jsonl
usage_log.jsonl         Generated at runtime -- one JSON line per Gemini call (gitignored)
```

This is a first-pass prototype: floors are modeled as aggregated data (not
10,000 individually simulated people), and numbers are tuned for game feel
rather than realism. Easy next steps: persistence/save-load, per-floor
population growth/decline, a richer event tree, and letting the AI call
tools directly instead of only advising.
