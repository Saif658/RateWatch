"""Built-in provider presets.

Each preset is the minimum data needed to authenticate a probe request:
- base_url: root of the API (no trailing slash)
- auth_header_format: a single header line, with '{key}' as the placeholder
  for the API key. e.g. "Authorization: Bearer {key}" or "x-api-key: {key}".
- test_endpoint: path appended to base_url for the probe (GET, cheap).
- extra_headers: optional dict of additional headers (e.g. anthropic-version).

Presets are best-effort defaults. If a provider's URL or header has changed,
the registered check will gracefully fall through to "limit info
unavailable, key is valid" rather than crash.
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
    },
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "auth_header_format": AUTH_X_API_KEY,
        "test_endpoint": "/v1/models",
        "extra_headers": {"anthropic-version": "2023-06-01"},
    },
    "nvidia-nim": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com",
        "auth_header_format": AUTH_X_GOOG_API_KEY,
        "test_endpoint": "/v1beta/models",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "mistral-codestral": {
        "base_url": "https://codestral.mistral.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "opencode-zen": {
        "base_url": "https://opencode.ai/zen/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "opencode-go": {
        "base_url": "https://opencode.ai/go/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "wafer": {
        "base_url": "https://api.wafer.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "kimi": {
        "base_url": "https://api.moonshot.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
    "z.ai": {
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "auth_header_format": AUTH_BEARER,
        "test_endpoint": "/models",
    },
}


def get_preset(name: str) -> dict | None:
    return PRESETS.get(name)


def list_preset_names() -> list[str]:
    return sorted(PRESETS.keys())
