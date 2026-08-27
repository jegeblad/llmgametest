"""Local LLM backend via Ollama (https://ollama.com), swapped in for
game/gemini_client.py by setting LLM_BACKEND=ollama -- see game/llm_client.py
for how the two get selected. Mirrors gemini_client's shape (MODEL_NAME,
OFFLINE_HINT, make_client, create_chat) so callers don't need to know which
backend is actually live.

Requires a local Ollama server already running (`ollama serve`, or the
Ollama desktop app) with the model pulled first (`ollama pull <model>`).
Point at a different model with OLLAMA_MODEL, or a non-default server with
OLLAMA_HOST. Defaults to gpt-oss:20b -- OpenAI's open-weight model sized to
fit comfortably in 16GB of RAM/VRAM, with native structured-output support
so it can fill the same enum-constrained JSON schema Gemini does here.
"""

import os

MODEL_NAME = os.environ.get("OLLAMA_MODEL", "gpt-oss:20b")
HOST = os.environ.get("OLLAMA_HOST", "http://localhost:11434")
OFFLINE_HINT = (
    f"make sure Ollama is running (`ollama serve`) with {MODEL_NAME} pulled "
    f"(`ollama pull {MODEL_NAME}`)"
)


def make_client():
    try:
        import ollama
    except ImportError:
        return None
    client = ollama.Client(host=HOST)
    try:
        client.list()  # cheap reachability check -- fails fast if no server is up
    except Exception:
        return None
    return client


class _Usage:
    """Duck-types google.genai's usage_metadata shape closely enough for
    game/usage.py to log it the same way regardless of backend."""

    def __init__(self, prompt_tokens: int, output_tokens: int):
        self.prompt_token_count = prompt_tokens
        self.candidates_token_count = output_tokens
        self.thoughts_token_count = 0


class _Response:
    def __init__(self, text: str, usage_metadata, thinking: str = None):
        self.text = text
        self.usage_metadata = usage_metadata
        # Both gpt-oss and Qwen3 reason before answering, whether or not
        # `think` is passed -- Ollama already separates that trace out of
        # `content` into its own field by default, so this is free to read.
        # gemini's response objects have no such attribute, so callers use
        # getattr(response, "thinking", None) to stay backend-agnostic.
        self.thinking = thinking


class _Chat:
    """Ollama's /api/chat is stateless per call, so unlike a google.genai
    chat session, history has to be tracked and resent here."""

    def __init__(self, client, model: str, system_instruction: str, json_schema: dict = None):
        self._client = client
        self._model = model
        self._schema = json_schema
        self._messages = [{"role": "system", "content": system_instruction}]

    def send_message(self, prompt: str) -> "_Response":
        self._messages.append({"role": "user", "content": prompt})
        kwargs = {"format": self._schema} if self._schema is not None else {}
        result = self._client.chat(model=self._model, messages=self._messages, **kwargs)
        content = result["message"]["content"]
        self._messages.append({"role": "assistant", "content": content})
        usage = _Usage(result.get("prompt_eval_count") or 0, result.get("eval_count") or 0)
        return _Response(content, usage, thinking=result["message"].get("thinking"))


def create_chat(client, system_instruction: str, json_schema: dict = None):
    return _Chat(client, MODEL_NAME, system_instruction, json_schema)
