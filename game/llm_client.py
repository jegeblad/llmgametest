"""Picks which LLM backend powers the Silo AI and character chats: Gemini
(cloud, default) or Ollama (local), based on LLM_BACKEND. Both
game/ai_advisor.py and game/character_ai.py go through this facade instead
of importing a specific backend module directly, so switching is a one-line
env var change -- LLM_BACKEND=ollama to go local, unset (or =gemini) to
swap straight back -- not a code change.

Text-to-speech (game/speech.py) is unaffected and stays on Gemini -- this
only covers text generation.
"""

import os

BACKEND = os.environ.get("LLM_BACKEND", "gemini").strip().lower()

if BACKEND == "ollama":
    from game import ollama_client as _impl
elif BACKEND == "gemini":
    from game import gemini_client as _impl
else:
    raise ValueError(f"Unknown LLM_BACKEND {BACKEND!r} -- expected 'gemini' or 'ollama'")

MODEL_NAME = _impl.MODEL_NAME
OFFLINE_HINT = _impl.OFFLINE_HINT
make_client = _impl.make_client
create_chat = _impl.create_chat
