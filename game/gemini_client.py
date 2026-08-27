"""Shared Gemini client setup, used by both the Silo AI and character chats.

Kept tiny and dependency-light: callers hold onto the returned client for
their own lifetime (letting it get garbage-collected closes its HTTP session
mid-game), and treat `None` as "no live client available" -- no API key, the
`google-genai` package isn't installed, or client construction failed --
falling back to canned/offline behavior.

`create_chat()` takes a plain JSON Schema dict (not a `google.genai` Schema
object), so a caller can build one schema and hand it to either this module
or `game/ollama_client.py` via `game/llm_client.py`, which picks the backend
-- see that module.
"""

import os

MODEL_NAME = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
OFFLINE_HINT = "set GEMINI_API_KEY"


def make_client():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return None
    try:
        from google import genai
    except ImportError:
        return None
    try:
        return genai.Client(api_key=api_key)
    except Exception:
        return None


def create_chat(client, system_instruction: str, json_schema: dict = None):
    """A persistent chat session, optionally constrained to a JSON schema.
    `json_schema` is a plain dict (standard JSON Schema shape: {"type":
    "object", "properties": {...}, "required": [...]}) -- converted here to
    the `google.genai.types.Schema` the SDK actually wants, since the schema
    itself is defined once, backend-agnostically, by the caller."""
    from google.genai import types
    config_kwargs = {"system_instruction": system_instruction}
    if json_schema is not None:
        config_kwargs["response_mime_type"] = "application/json"
        config_kwargs["response_schema"] = _to_genai_schema(json_schema)
    return client.chats.create(model=MODEL_NAME, config=types.GenerateContentConfig(**config_kwargs))


def _to_genai_schema(json_schema: dict):
    """Recursive converter, only as capable as our actual schemas need --
    objects with string (optionally enum) properties. Extend if a future
    schema needs arrays or nesting."""
    from google.genai import types
    if json_schema.get("type") == "object":
        return types.Schema(
            type=types.Type.OBJECT,
            properties={k: _to_genai_schema(v) for k, v in json_schema["properties"].items()},
            required=json_schema.get("required"),
        )
    return types.Schema(
        type=types.Type.STRING,
        enum=json_schema.get("enum"),
        description=json_schema.get("description"),
    )
