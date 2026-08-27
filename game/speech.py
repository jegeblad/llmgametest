"""Gemini-based text-to-speech for the Silo AI and the five characters.

Generates real audio via Gemini's TTS model, reusing the same API key and
client pattern as the chat models -- not the browser's built-in (robotic)
Web Speech API. A short natural-language style instruction is prepended to
the text before synthesis; Gemini TTS treats a "Say in an X tone:" prefix
as delivery guidance and does not speak it aloud (confirmed empirically by
comparing output durations with/without the prefix), so a character's live
mood can drive their delivery without any audio post-processing.

Mechanics mirror the rest of the app's AI plumbing: queue() stashes text
during a script run, grouped by speaker (a single cycle can produce more
than one Silo-AI-voiced message -- a Continuity Protocol alert plus the
regular status report -- and those get spoken as one combined clip rather
than overlapping). render_player() -- called once, at the very end of that
run, and before any early `st.stop()` -- flushes the queue, synthesizes
one audio clip per speaker, and autoplays it.
"""

import io
import os
import re
import wave
from typing import Optional

import streamlit as st

from game import gemini_client, usage

_MARKDOWN_STRIP_RE = re.compile(r"[*_`#]+")


def _clean_for_speech(text: str) -> str:
    text = _MARKDOWN_STRIP_RE.sub("", text)
    return " ".join(text.split())

TTS_MODEL_NAME = os.environ.get("GEMINI_TTS_MODEL", "gemini-2.5-flash-preview-tts")

# Six distinct prebuilt Gemini voices, one per persona. All verified live
# against the API; feel free to swap in any of Gemini's other prebuilt
# voice names (see Gemini API docs) if a different pairing sounds better.
VOICE_NAMES = {
    "silo_ai": "Charon",
    "Dr. Elena Reyes": "Leda",
    "Marcus Webb": "Fenrir",
    "Priya Anand": "Orus",
    "Tomas Okafor": "Puck",
    "Sasha Kim": "Kore",
}

_MOOD_STYLE = {
    "happy": "warm and a little upbeat",
    "grumpy": "short-tempered and terse",
    "concerned": "wary and a little uneasy",
    "frustrated": "tense and clipped",
    "tired": "worn out, noticeably slower than usual",
    "hungry": "distracted and a bit strained",
}

# Default delivery style applied when a speaker's queue() call doesn't pass
# its own (characters always do, via mood_style() -- this only ever fires
# for "silo_ai"). Verified empirically, not just written and hoped for: on
# the Charon voice, "rapid-fire" phrasing measurably cuts clip duration by
# ~35% (reproduced across repeated runs of the same line), and the deep/flat
# framing measurably drops median pitch and cuts pitch variance versus no
# style at all -- i.e. actually faster and flatter/more synthetic-sounding,
# not just adjectives hoping to be true.
_DEFAULT_STYLE = {
    "silo_ai": (
        "fast and clipped -- rapid-fire, no pauses for warmth -- in a deep, "
        "flat, mechanical monotone, blunt and unfriendly"
    ),
}

_SAMPLE_RATE = 24000  # Gemini TTS output: mono, 16-bit PCM, 24kHz (audio/L16;rate=24000)


class GeminiTTS:
    def __init__(self):
        self._client = gemini_client.make_client()
        self.online = self._client is not None

    def synthesize(self, speaker_key: str, text: str, style: str = "") -> Optional[bytes]:
        """Returns a playable WAV file's bytes, or None if unavailable/failed."""
        if not self.online or not text.strip():
            return None
        voice = VOICE_NAMES.get(speaker_key, "Kore")
        style = style or _DEFAULT_STYLE.get(speaker_key, "")
        prompt = f"Say {style}: {text}" if style else text
        try:
            from google.genai import types
            response = self._client.models.generate_content(
                model=TTS_MODEL_NAME,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
                        )
                    ),
                ),
            )
            usage.record(TTS_MODEL_NAME, getattr(response, "usage_metadata", None), speaker=speaker_key)
            pcm = response.candidates[0].content.parts[0].inline_data.data
        except Exception:
            return None
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(_SAMPLE_RATE)
            wav_file.writeframes(pcm)
        return buf.getvalue()


def mood_style(mood: str) -> str:
    return _MOOD_STYLE.get(mood, "")


def init_state() -> None:
    st.session_state.setdefault("speech_enabled", True)
    st.session_state.setdefault("speech_queue", [])
    if "tts" not in st.session_state:
        st.session_state.tts = GeminiTTS()


def queue(speaker_key: str, text: str, style: str = "") -> None:
    """Queue text to be spoken once render_player() runs this pass, if
    read-aloud is currently enabled. speaker_key is "silo_ai" or a
    character's full name (see VOICE_NAMES)."""
    if not st.session_state.get("speech_enabled"):
        return
    text = _clean_for_speech(text)
    if not text:
        return
    st.session_state.setdefault("speech_queue", []).append(
        {"speaker": speaker_key, "text": text, "style": style}
    )


def render_player() -> None:
    """Flush queued speech: one combined clip per speaker, autoplayed.
    Call once per script run, after all queue() calls -- including right
    before any early `st.stop()`, since code after st.stop() never runs."""
    items = st.session_state.get("speech_queue", [])
    if not items:
        return
    st.session_state.speech_queue = []

    tts = st.session_state.get("tts")
    if tts is None or not tts.online:
        return

    by_speaker = {}
    for item in items:
        group = by_speaker.setdefault(item["speaker"], {"text": [], "style": item["style"]})
        group["text"].append(item["text"])

    for speaker, group in by_speaker.items():
        combined = " ... ".join(group["text"])
        with st.spinner("Generating voice..."):
            wav_bytes = tts.synthesize(speaker, combined, group["style"])
        if wav_bytes:
            st.audio(wav_bytes, format="audio/wav", autoplay=True)


def render_controls() -> None:
    """Sidebar toggle. Call inside `with st.sidebar:`."""
    st.session_state.speech_enabled = st.checkbox(
        "🔊 Read responses aloud (Gemini voices)",
        value=st.session_state.get("speech_enabled", True),
    )
    tts = st.session_state.get("tts")
    if st.session_state.speech_enabled and tts is not None and not tts.online:
        st.caption("Voice unavailable — GEMINI_API_KEY not set.")
