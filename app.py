"""Silo: a resource-management prototype, Streamlit UI.

You are the Head of IT in an underground silo sealed off from the outside
world, home to roughly 10,000 people spread across 200 floors. The Silo AI
has full sensor access and will advise you, but only you can issue the
directives that keep people fed, watered, breathing, and (relatively) calm
-- and it also administers the Continuity Protocol, a fail-safe permitting
it to act on the population directly if you don't.

Run `streamlit run app.py`. Set GEMINI_API_KEY in your environment (or a
.env file) to enable the live AI advisor; without it the game still runs
using a canned telemetry readout instead. Set LLM_BACKEND=ollama to use a
local model via Ollama instead of Gemini for the Silo AI and character
chats -- see game/llm_client.py.
"""

import time

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import pandas as pd
import streamlit as st

from game import actions, characters, events, failsafe, llm_client, silo_view, speech, usage
from game import constants as C
from game.ai_advisor import SiloAI
from game import avatar
from game.character_ai import CharacterAI, CharacterReaction, describe_pose
from game.simulation import advance_cycle, init_silo

WIN_CYCLE = 60

st.set_page_config(page_title="SILO — Head of IT", page_icon="🔒", layout="wide")


# --- session / game lifecycle -----------------------------------------------

def init_game():
    state = init_silo()
    ai = SiloAI()
    chat_log = []
    report = ai.status_report(state, list(state.history))
    chat_log.append({"role": "assistant", "content": report, "kind": "report"})
    speech.queue("silo_ai", report)
    st.session_state.state = state
    st.session_state.ai = ai
    st.session_state.chat_log = chat_log
    st.session_state.recent_events = list(state.history)
    st.session_state.won_announced = False
    st.session_state.char_ai = CharacterAI()
    st.session_state.character_chat_logs = {ch.name: [] for ch in state.characters}
    st.session_state.character_last_reaction = {ch.name: CharacterReaction(text="") for ch in state.characters}


def check_population_collapse(state):
    """Fallback loss condition for outcomes the Continuity Protocol doesn't
    itself cause -- e.g. starving/oxygen-death attrition grinding the
    population down without stability/morale ever crossing its thresholds."""
    if not state.game_over and state.population <= 1000:
        state.game_over = True
        state.game_over_reason = (
            f"Population has fallen to {state.population}. Life support cannot "
            "sustain the remaining survivors, and silo command structure collapses."
        )


def do_advance_cycle():
    """Advance the simulation by one cycle. Deliberately does NOT call the
    Silo AI -- that only happens on demand (a chat question, or the
    "Request Status Report" button), so this stays cheap and local, which
    is what makes real-time auto-advance (see render_realtime_tick) viable
    at all: no per-cycle network call blocking the loop."""
    state = st.session_state.state

    cycle_events = advance_cycle(state)
    cycle_events += events.roll_random_events(state)
    cycle_events += events.update_unrest_and_riots(state)
    for e in cycle_events:
        state.log(e)

    characters.advance(state)
    characters.compute_moods(state)

    # Protocol events are pre-written by failsafe.py, not LLM-generated --
    # no extra text-generation cost to narrate them, and they're rare
    # (only fire on arm/cull/terminate), so still worth the small TTS cost.
    protocol_events = failsafe.evaluate(state)
    for e in protocol_events:
        state.log(e)
        st.session_state.chat_log.append({"role": "assistant", "content": e, "kind": "protocol"})
        speech.queue("silo_ai", e)

    check_population_collapse(state)
    st.session_state.recent_events = cycle_events

    if state.cycle >= WIN_CYCLE and not st.session_state.won_announced:
        st.session_state.won_announced = True
        st.session_state.chat_log.append({
            "role": "assistant",
            "kind": "milestone",
            "content": (
                f"You have kept the silo stable for {WIN_CYCLE} cycles. "
                "The people are alive. The watch continues."
            ),
        })


# --- rendering helpers -------------------------------------------------------

def _vital_bar(container, label, value):
    color = "#3fb950" if value >= 60 else ("#d29922" if value >= 30 else "#f85149")
    container.markdown(
        f"""
        <div style="margin-bottom:2px;font-size:0.9em">{label}: <b>{value:.0f}/100</b></div>
        <div style="background:#30363d;border-radius:6px;height:14px;width:100%;overflow:hidden;">
          <div style="background:{color};width:{value}%;height:100%;"></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_dashboard(state):
    st.title("SILO")
    st.caption(f"Head of IT Console — Cycle {state.cycle} — Population {state.population:,}")

    if not st.session_state.ai.online:
        st.warning(
            f"Silo AI advisor is offline — {llm_client.OFFLINE_HINT} to enable live advice. "
            "Falling back to raw telemetry summaries.",
            icon="⚠️",
        )

    if state.protocol_armed:
        remaining = max(0, (state.protocol_deadline_cycle or state.cycle) - state.cycle)
        st.error(
            f"⚠ CONTINUITY PROTOCOL ARMED — {remaining} cycle(s) remain before it acts. "
            f"{state.culls_executed} prior corrective action(s) on record.",
            icon="⚠️",
        )

    res = state.resources
    pop = state.population

    def days(reserve, per_person):
        return reserve / (pop * per_person) if pop and per_person else 0.0

    st.subheader("Resources")
    cols = st.columns(5)
    cols[0].metric("Food", f"{res.food:,.0f}", f"{days(res.food, C.FOOD_PER_PERSON):.1f} days")
    cols[1].metric("Water", f"{res.water:,.0f}", f"{days(res.water, C.WATER_PER_PERSON):.1f} days")
    cols[2].metric("Oxygen", f"{res.oxygen:,.0f}", f"{days(res.oxygen, C.OXYGEN_PER_PERSON):.1f} days")
    cols[3].metric("Fuel", f"{res.fuel:,.0f}")
    cols[4].metric("Power", f"{res.power_ratio*100:.0f}%", "of demand")

    st.subheader("Vitals")
    vcols = st.columns(3)
    _vital_bar(vcols[0], "Morale", res.morale)
    _vital_bar(vcols[1], "Stability", res.stability)
    _vital_bar(vcols[2], "Public Health", res.health)

    st.caption(f"Ration level: **{state.ration_level}**  ·  Power priority: **{state.power_priority}**")


def render_events(recent_events):
    if not recent_events:
        return
    with st.expander(f"Cycle Events ({len(recent_events)})", expanded=True):
        for e in recent_events:
            st.markdown(f"- {e}")


def render_silo_diagram(state):
    st.subheader("Silo Cross-Section")
    svg = silo_view.render(state)
    st.markdown(
        f'<div style="max-height:640px; overflow-y:auto; overflow-x:hidden; '
        f'border:1px solid #30363d; border-radius:6px; padding:10px 4px; background:#0d1117;">'
        f'{svg}</div>',
        unsafe_allow_html=True,
    )

    legend_cols = st.columns(len(silo_view.ZONE_COLORS) + 2)
    for col, (zone, color) in zip(legend_cols, silo_view.ZONE_COLORS.items()):
        col.markdown(
            f'<span style="color:{color}">■</span> {silo_view.ZONE_LABELS[zone]}',
            unsafe_allow_html=True,
        )
    legend_cols[-2].markdown(
        f'<span style="color:{silo_view.STATUS_WARNING}">▢</span> Degraded / elevated unrest',
        unsafe_allow_html=True,
    )
    legend_cols[-1].markdown(
        f'<span style="color:{silo_view.STATUS_CRITICAL}">▢</span> Critical',
        unsafe_allow_html=True,
    )
    st.caption("Hover any floor for exact stats. Colored dots are personnel — see below.")


def render_personnel(state):
    st.subheader("Personnel")
    st.caption("Talk to them in the chat panel on the left.")
    cols = st.columns(len(state.characters))
    for col, ch in zip(cols, state.characters):
        mood_emoji = characters.MOOD_EMOJI.get(ch.mood, "")
        col.markdown(
            f'<div style="border:1px solid {ch.color};border-radius:6px;padding:8px;text-align:center;">'
            f'<div style="width:30px;height:30px;border-radius:50%;background:{ch.color};'
            f'color:#0d1117;font-weight:bold;display:flex;align-items:center;justify-content:center;'
            f'margin:0 auto 6px;font-size:0.8em;">{ch.initials}</div>'
            f'<div style="font-size:0.85em"><b>{ch.name}</b>, {ch.age}</div>'
            f'<div style="font-size:0.75em;color:#8b949e">{ch.role}</div>'
            f'<div style="font-size:0.8em;margin-top:4px;">Floor {ch.floor}</div>'
            f'<div style="font-size:0.85em;margin-top:4px;" title="{ch.mood_reason}">{mood_emoji} {ch.mood}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


def render_floors(state):
    with st.expander("📋 Floor Data Table (sortable / filterable)"):
        type_names = sorted({f.type.value for f in state.floors})
        choice = st.selectbox("Filter by type", ["All"] + type_names)
        floors = state.floors if choice == "All" else [f for f in state.floors if f.type.value == choice]

        df = pd.DataFrame([
            {
                "#": f.number,
                "Type": f.type.value,
                "Population": f.population,
                "Condition": f.condition,
                "Unrest": f.unrest,
                "Status": f.status,
            }
            for f in floors
        ])
        st.dataframe(
            df,
            hide_index=True,
            width="stretch",
            column_config={
                "Condition": st.column_config.ProgressColumn("Condition", min_value=0, max_value=100, format="%.0f%%"),
                "Unrest": st.column_config.ProgressColumn("Unrest", min_value=0, max_value=100, format="%.0f"),
            },
        )
        st.caption("Tip: click a column header to sort — e.g. Condition ascending to find the worst floors.")

        st.markdown("**Inspect a floor**")
        floor_n = st.number_input("Floor number", 1, C.NUM_FLOORS, 1, key="inspect_floor")
        f = state.floor(floor_n)
        st.markdown(
            f"**Floor {f.number} — {f.type.value}**\n\n"
            f"Population: {f.population}  \n"
            f"Condition: {f.condition:.0f}% ({f.status})  \n"
            f"Unrest: {f.unrest:.0f}/100  \n"
            f"Health: {f.health:.0f}/100"
        )
        if f.log:
            st.markdown("Recent log:\n" + "\n".join(f"- {l}" for l in f.log))


def render_ai_chat(state, ai):
    st.subheader("SILO AI" + ("" if ai.online else " (offline fallback)"))
    st.caption(
        "The Silo AI isn't consulted automatically each cycle anymore — ask it something, "
        "or request a fresh situation report below."
    )
    if st.button("📋 Request Status Report", key="request_status_report"):
        with st.spinner("Silo AI processing..."):
            report = ai.status_report(state, st.session_state.recent_events)
        st.session_state.chat_log.append({
            "role": "assistant", "content": report, "kind": "report", "thinking": ai.last_thinking,
        })
        speech.queue("silo_ai", report)
        st.rerun()

    for msg in st.session_state.chat_log[-24:]:
        role = msg["role"]
        kind = msg.get("kind", "chat")
        avatar = "🛑" if kind == "protocol" else ("🤖" if role == "assistant" else "🧑‍💻")
        with st.chat_message(role, avatar=avatar):
            if kind == "protocol":
                st.markdown(f":red[**CONTINUITY PROTOCOL**]\n\n{msg['content']}")
            elif kind == "milestone":
                st.markdown(f":green[{msg['content']}]")
            else:
                st.markdown(msg["content"])
            if msg.get("thinking"):
                with st.expander("🧠 Thinking"):
                    st.caption(msg["thinking"])

    question = st.chat_input("Ask the Silo AI...")
    if question:
        st.session_state.chat_log.append({"role": "user", "content": question, "kind": "chat"})
        with st.spinner("Silo AI processing..."):
            answer = ai.ask(state, question)
        st.session_state.chat_log.append({
            "role": "assistant", "content": answer, "kind": "chat", "thinking": ai.last_thinking,
        })
        speech.queue("silo_ai", answer)
        st.rerun()


def render_character_chat(state, char_ai, ch):
    mood_emoji = characters.MOOD_EMOJI.get(ch.mood, "")
    online_note = "" if char_ai.online else " (offline fallback)"

    reaction = st.session_state.character_last_reaction.get(ch.name) or CharacterReaction(text="")
    col_avatar, col_info = st.columns([1, 2.2])
    with col_avatar:
        avatar_html, avatar_height = avatar.render_animated_html(reaction, ch)
        st.components.v1.html(avatar_html, height=avatar_height)
    with col_info:
        st.markdown(f"**{ch.name}**, {ch.age} — {ch.role}{online_note}")
        st.caption(f"{mood_emoji} Feeling **{ch.mood}** — {ch.mood_reason}  ·  currently on Floor {ch.floor}")
        if reaction.text:
            st.caption(f"🎭 {describe_pose(reaction)}")

    log = st.session_state.character_chat_logs.setdefault(ch.name, [])
    for msg in log[-24:]:
        avatar_icon = ch.avatar if msg["role"] == "assistant" else "🧑‍💻"
        with st.chat_message(msg["role"], avatar=avatar_icon):
            st.markdown(msg["content"])
            if msg.get("pose_caption"):
                st.caption(f"🎭 {msg['pose_caption']}")
            if msg.get("thinking"):
                with st.expander("🧠 Thinking"):
                    st.caption(msg["thinking"])

    question = st.chat_input(f"Talk to {ch.name.split()[-1]}...", key=f"char_chat_input_{ch.name}")
    if question:
        log.append({"role": "user", "content": question})
        with st.spinner(f"{ch.name.split()[-1]} is responding..."):
            reaction = char_ai.ask(state, ch, question)
        answer = reaction.text
        log.append({
            "role": "assistant", "content": answer,
            "pose_caption": describe_pose(reaction), "thinking": reaction.thinking,
        })
        st.session_state.character_last_reaction[ch.name] = reaction
        speech.queue(ch.name, answer, style=speech.mood_style(ch.mood))
        st.rerun()


_TICK_INTERVALS = [1, 2, 3, 5, 10, 15, 30]


def render_realtime_controls(state):
    st.markdown("### ⏱ Real-Time Mode")
    was_enabled = st.session_state.get("realtime_enabled", False)
    st.session_state.realtime_enabled = st.checkbox("▶ Auto-advance cycles", value=was_enabled)
    if st.session_state.realtime_enabled and not was_enabled:
        # Just turned on: start the clock now. Without this, the missing
        # timestamp would look like "infinite time has passed" to the tick
        # gate below and fire an instant extra cycle before ever waiting a
        # full interval.
        st.session_state.realtime_last_tick = time.monotonic()
    if st.session_state.realtime_enabled:
        st.session_state.realtime_interval = st.select_slider(
            "Tick interval",
            options=_TICK_INTERVALS,
            value=st.session_state.get("realtime_interval", 5),
            format_func=lambda s: f"{s}s",
        )
        st.caption(
            "Cycles advance on their own. The Silo AI stays quiet during this — "
            "ask it something or request a report anytime."
        )


def render_realtime_tick(state):
    """A near-invisible fragment that re-fires itself on a timer (Streamlit's
    native `run_every`) and, each time it does, advances one cycle and forces
    a full-page rerun so the rest of the UI reflects it. Only armed while
    real-time mode is on and the game isn't over, so it stops cleanly the
    moment either becomes false -- no fragment gets (re)created to keep
    ticking in the background otherwise.

    The `st.rerun()` below is necessary (a fragment's own re-execution only
    refreshes the fragment itself, not the rest of the dashboard) but it has
    a sharp edge: it forces the *whole script* to run again immediately,
    which reaches this same call site synchronously, not on `run_every`'s
    schedule -- so without a real wall-clock gate this cascades into a tight
    loop with no actual delay (confirmed live: 24 cycles firing almost
    instantly). The `realtime_last_tick` check is what actually paces it;
    `run_every` alone does not.
    """
    if not st.session_state.get("realtime_enabled") or state.game_over:
        return
    interval = st.session_state.get("realtime_interval", 5)

    @st.fragment(run_every=f"{interval}s")
    def _tick():
        live_state = st.session_state.state
        if not st.session_state.get("realtime_enabled") or live_state.game_over:
            return
        now = time.monotonic()
        last_tick = st.session_state.get("realtime_last_tick", 0.0)
        if now - last_tick < interval:
            return  # this invocation wasn't the timer -- a cascaded rerun, or too soon
        st.session_state.realtime_last_tick = now
        do_advance_cycle()
        st.rerun()

    _tick()


def render_sidebar(state):
    with st.sidebar:
        st.markdown("## IT Console")
        st.caption(f"Cycle {state.cycle} · Population {state.population:,}")

        if st.button("⏭  Advance Cycle", type="primary", width="stretch"):
            do_advance_cycle()

        render_realtime_controls(state)

        speech.render_controls()
        usage.render_summary()

        st.divider()

        with st.expander("🛠 Maintenance"):
            floor_n = st.number_input("Floor", 1, C.NUM_FLOORS, 1, key="repair_floor")
            if st.button("Dispatch Maintenance", key="repair_btn", width="stretch"):
                _run_action(actions.dispatch_maintenance, state, floor_n)

        with st.expander("🛡 Security"):
            floor_n = st.number_input("Floor", 1, C.NUM_FLOORS, 1, key="security_floor")
            if st.button("Deploy Security", key="security_btn", width="stretch"):
                _run_action(actions.deploy_security, state, floor_n)

        with st.expander("🍽 Rationing"):
            levels = list(C.RATION_LEVELS.keys())
            level = st.selectbox("Ration level", levels, index=levels.index(state.ration_level))
            if st.button("Apply Ration Level", key="ration_btn", width="stretch"):
                _run_action(actions.set_ration_level, state, level)

        with st.expander("⚡ Power Routing"):
            priority = st.selectbox(
                "Priority", C.POWER_PRIORITIES, index=C.POWER_PRIORITIES.index(state.power_priority)
            )
            if st.button("Apply Power Priority", key="power_btn", width="stretch"):
                _run_action(actions.set_power_priority, state, priority)

        with st.expander("📢 Broadcast"):
            tone = st.selectbox("Tone", list(C.BROADCAST_TONES.keys()))
            if st.button("Send Broadcast", key="broadcast_btn", width="stretch"):
                _run_action(actions.broadcast_announcement, state, tone)

        with st.expander("🔒 Lockdown"):
            floor_n = st.number_input("Floor", 1, C.NUM_FLOORS, 1, key="lockdown_floor")
            col1, col2 = st.columns(2)
            if col1.button("Engage", key="lockdown_on_btn", width="stretch"):
                _run_action(actions.lockdown_floor, state, floor_n, True)
            if col2.button("Lift", key="lockdown_off_btn", width="stretch"):
                _run_action(actions.lockdown_floor, state, floor_n, False)


def _run_action(fn, *args):
    try:
        msg = fn(*args)
        st.success(msg, icon="✅")
    except actions.ActionError as e:
        st.error(str(e), icon="⚠️")


def render_game_over(reason):
    st.markdown("## 💀 SILO FAILURE")
    st.error(reason)
    if st.button("Restart Silo", type="primary"):
        # Usage/cost tracking is about real money spent, not game state --
        # it survives a restart on purpose, unlike everything else here.
        preserved = {"usage_by_model"}
        for key in list(st.session_state.keys()):
            if key not in preserved:
                del st.session_state[key]
        st.rerun()


# --- main --------------------------------------------------------------------

usage.init_state()
speech.init_state()

if "state" not in st.session_state:
    init_game()

state = st.session_state.state
ai = st.session_state.ai

if state.game_over:
    render_game_over(state.game_over_reason)
    speech.render_player()
    st.stop()

render_sidebar(state)  # may itself end the game via "Advance Cycle" -> re-check below

if state.game_over:
    render_game_over(state.game_over_reason)
    speech.render_player()
    st.stop()

render_realtime_tick(state)

render_dashboard(state)
render_events(st.session_state.recent_events)

col_mid, col_right = st.columns([1.15, 1], gap="large")
with col_mid:
    tab_labels = ["🤖 Silo AI"] + [
        f"{characters.MOOD_EMOJI.get(ch.mood, '')} {ch.name.split()[-1]}" for ch in state.characters
    ]
    tabs = st.tabs(tab_labels)
    with tabs[0]:
        render_ai_chat(state, ai)
    for tab, ch in zip(tabs[1:], state.characters):
        with tab:
            render_character_chat(state, st.session_state.char_ai, ch)
with col_right:
    render_silo_diagram(state)
    render_personnel(state)

render_floors(state)
speech.render_player()
