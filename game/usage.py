"""All-time token-usage and estimated-cost tracking for every Gemini API
call the app makes (Silo AI, character chats, and TTS), based on each
response's `usage_metadata`.

The log file (`usage_log.jsonl`, one JSON object per call, at the project
root) is the source of truth -- not `st.session_state`, which resets per
browser session. `init_state()` seeds session_state by summing the file
once per session (cheap unless the log gets huge); `record()` updates
session_state immediately *and* appends a line to the file, so the two
stay in sync within a run and every session contributes to the same
all-time total. Concurrent sessions writing at the same instant could each
overwrite the other's totals were the file itself being read-and-rewritten,
which is why this appends one line per call instead -- appends of a single
line this short are atomic on any filesystem we care about here.

This is an estimate, not an invoice: it's built from real token counts
returned by the API (not guessed), converted at the current published
per-model rates below -- but Google's own billing dashboard is always the
source of truth. Thinking tokens (`thoughts_token_count`) are billed at
the output rate per Google's pricing page, but reported as a separate
field from `candidates_token_count` by the SDK, so both are folded into
"output tokens" here for cost purposes.
"""

import json
from datetime import datetime, timezone
from pathlib import Path

import streamlit as st

LOG_PATH = Path(__file__).resolve().parent.parent / "usage_log.jsonl"

# USD per 1,000,000 tokens. Source: https://ai.google.dev/gemini-api/docs/pricing
# (checked 2026-08-11; cross-referenced against a second independent source).
# Update this table if pricing changes, or add an entry if GEMINI_MODEL /
# GEMINI_TTS_MODEL is overridden to a model not listed here -- usage for an
# unlisted model still gets counted, just not priced.
PRICING = {
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    "gemini-2.5-flash-preview-tts": {"input": 0.50, "output": 10.00},
}


def _empty_bucket() -> dict:
    return {"calls": 0, "input_tokens": 0, "output_tokens": 0}


def _load_totals_from_log() -> dict:
    """Sum every line ever logged into per-model totals. Skips (rather
    than crashes on) any malformed line -- e.g. a half-written line from
    a killed process."""
    totals_by_model: dict = {}
    if not LOG_PATH.exists():
        return totals_by_model
    with open(LOG_PATH, "r") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                bucket = totals_by_model.setdefault(entry["model"], _empty_bucket())
                bucket["calls"] += 1
                bucket["input_tokens"] += entry.get("input_tokens", 0)
                bucket["output_tokens"] += entry.get("output_tokens", 0)
            except (json.JSONDecodeError, KeyError):
                continue
    return totals_by_model


def _append_log_entry(model_name: str, speaker: str, input_tokens: int, output_tokens: int) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": model_name,
        "speaker": speaker,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }
    try:
        with open(LOG_PATH, "a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        pass  # tracking is a nice-to-have; never let a disk hiccup break the game


def init_state() -> None:
    """Seed session_state with the all-time totals from disk, once per
    session -- safe to call every run, since it's a no-op after the first."""
    if "usage_by_model" not in st.session_state:
        st.session_state.usage_by_model = _load_totals_from_log()


def record(model_name: str, usage_metadata, speaker: str = "") -> None:
    """Call with the model name used for the request, the response's
    `usage_metadata` (safe to pass None, e.g. if a call raised before
    returning one -- it's just a no-op), and optionally who/what the call
    was for (e.g. "silo_ai" or a character's name), logged for reference."""
    if usage_metadata is None:
        return
    input_tokens = getattr(usage_metadata, "prompt_token_count", None) or 0
    output_tokens = (getattr(usage_metadata, "candidates_token_count", None) or 0) + (
        getattr(usage_metadata, "thoughts_token_count", None) or 0
    )

    bucket = st.session_state.setdefault("usage_by_model", {}).setdefault(model_name, _empty_bucket())
    bucket["calls"] += 1
    bucket["input_tokens"] += input_tokens
    bucket["output_tokens"] += output_tokens

    _append_log_entry(model_name, speaker, input_tokens, output_tokens)


def _cost_for(model_name: str, bucket: dict) -> float:
    rates = PRICING.get(model_name)
    if not rates:
        return 0.0
    return (
        bucket["input_tokens"] / 1_000_000 * rates["input"]
        + bucket["output_tokens"] / 1_000_000 * rates["output"]
    )


def estimated_cost_usd() -> float:
    return sum(
        _cost_for(model_name, bucket)
        for model_name, bucket in st.session_state.get("usage_by_model", {}).items()
    )


def totals():
    """Returns (total_calls, total_input_tokens, total_output_tokens)."""
    buckets = st.session_state.get("usage_by_model", {}).values()
    return (
        sum(b["calls"] for b in buckets),
        sum(b["input_tokens"] for b in buckets),
        sum(b["output_tokens"] for b in buckets),
    )


def render_summary() -> None:
    """Sidebar widget. Call inside `with st.sidebar:`."""
    calls, inp, out = totals()
    cost = estimated_cost_usd()
    total_tokens = inp + out
    with st.expander(f"💳 API usage — ~${cost:.4f} · {total_tokens:,} tokens", expanded=False):
        if calls == 0:
            st.caption("No Gemini calls logged yet.")
            return
        st.caption(
            f"All-time, across every session — {calls} call(s) · "
            f"{inp:,} input tokens · {out:,} output tokens"
        )
        for model_name, bucket in st.session_state.get("usage_by_model", {}).items():
            model_cost = _cost_for(model_name, bucket)
            pricing_note = "" if model_name in PRICING else " (pricing unknown)"
            st.markdown(
                f"**{model_name}**{pricing_note}  \n"
                f"{bucket['calls']} calls · {bucket['input_tokens']:,} in / "
                f"{bucket['output_tokens']:,} out → ${model_cost:.4f}"
            )
        st.caption(
            f"Estimate from logged token counts, at current published rates — not Google's "
            f"actual invoice. Logged to `{LOG_PATH.name}`."
        )
