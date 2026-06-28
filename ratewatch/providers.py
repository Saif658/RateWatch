"""Built-in provider presets.

Each preset is the minimum data needed to authenticate a probe request:
- base_url: root of the API (no trailing slash)
- auth_header_format: a single header line, with '{key}' as the placeholder
  for the API key. e.g. "Authorization: Bearer {key}" or "x-api-key: {key}".
- test_endpoint: path appended to base_url for the cheap probe (GET, /models).
- extra_headers: optional dict of additional headers (e.g. anthropic-version).
- chat_model: cheapest available chat model id; used by --live mode.
- chat_endpoint: path appended to base_url for live chat requests. Defaults
  to "/chat/completions" (OpenAI-compatible), so most presets omit it.
- chat_format: request/response shape of the live chat endpoint.
  Defaults to "openai". "anthropic" mirrors OpenAI messages but POSTs to
  /v1/messages; "gemini" uses Gemini's native generateContent shape, with
  the model substituted into the URL path.

Presets are best-effort defaults. If a provider's URL, header, or model id
has changed, the registered check will gracefully fall through to "limit
info unavailable, key is valid" rather than crash.
"""

from __future__ import annotations

AUTH_BEARER = "Authorization: Bearer {key}"
AUTH_X_API_KEY = "x-api-key: {key}"
AUTH_X_GOOG_API_KEY = "x-goog-api-key: {key}"


PRESETS: dict[str, dict] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "gpt-4o-mini",
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "auth_header_format": AUTH_X_API_KEY,
        "test_endpoint": "/v1/models",
        "extra_headers": {"anthropic-version": "2023-06-01"},
        "chat_model": "claude-haiku-4-5",
        "chat_endpoint": "/v1/messages",
        "chat_format": "anthropic",
    },
    "nvidia-nim": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "meta/llama-3.1-8b-instruct",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "meta-llama/llama-3.1-8b-instruct:free",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com",
        "auth_header_format": AUTH_X_GOOG_API_KEY,
        "test_endpoint": "/v1beta/models",
        "chat_model": "gemini-2.0-flash-lite",
        "chat_endpoint": "/v1beta/models/{model}:generateContent",
        "chat_format": "gemini",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "deepseek-chat",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "open-mistral-7b",
    },
    "mistral-codestral": {
        "base_url": "https://codestral.mistral.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "codestral-latest",
    },
    "opencode-zen": {
        "base_url": "https://opencode.ai/zen/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "kimi-k2",
    },
    "opencode-go": {
        "base_url": "https://opencode.ai/go/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "kimi-k2",
    },
    "wafer": {
        "base_url": "https://api.wafer.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "meta-llama/llama-3.1-8b-instruct",
    },
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "moonshot-v1-8k",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "llama-3.1-8b",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "llama-3.1-8b-instant",
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "accounts/fireworks/models/llama-v3p1-8b-instruct",
    },
    "z.ai": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
        "chat_model": "glm-4-flash",
    },
}


def get_preset(name: str) -> dict | None:
    return PRESETS.get(name)


def list_preset_names() -> list[str]:
    return sorted(PRESETS.keys())
