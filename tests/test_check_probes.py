"""HTTP-mocked tests for ratewatch.check probe functions.

Uses the `responses` library to intercept every requests call — no real
network. Covers the four outcomes the CLI cares about:
- 2xx with rate-limit headers  → status (ok / warn / limited)
- 2xx without rate-limit headers → unknown
- 429                            → limited
- 4xx (auth / other)             → error
- network exception              → error
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests
import responses

from ratewatch import check


# A baseline provider config used by most tests.
CFG = {
    "base_url": "https://api.example.com/v1",
    "auth_header_format": "Authorization: Bearer {key}",
    "test_endpoint": "/models",
}


# ===========================================================================
# check_provider (cheap GET probe)
# ===========================================================================

class TestCheckProvider:
    @responses.activate
    def test_success_with_full_headers(self) -> None:
        responses.get(
            "https://api.example.com/v1/models",
            json={"data": []},
            status=200,
            headers={
                "x-ratelimit-remaining-requests": "60",
                "x-ratelimit-limit-requests": "100",
                "x-ratelimit-reset-requests": "30",
            },
        )
        result = check.check_provider("example", CFG, "sk-test")

        assert result.provider == "example"
        assert result.status == check.STATUS_OK
        assert result.remaining == 60
        assert result.limit == 100
        assert result.reset_seconds == 30
        assert not result.is_error
        assert not result.is_limited

    @responses.activate
    def test_success_with_warn_remaining(self) -> None:
        responses.get(
            "https://api.example.com/v1/models",
            json={},
            status=200,
            headers={
                "x-ratelimit-remaining-requests": "5",
                "x-ratelimit-limit-requests": "100",
            },
        )
        result = check.check_provider("example", CFG, "sk-test")
        assert result.status == check.STATUS_WARN

    @responses.activate
    def test_success_without_rate_limit_headers_is_unknown(self) -> None:
        # Valid 200, but provider didn't hand us any rate-limit info.
        responses.get(
            "https://api.example.com/v1/models",
            json={"data": []},
            status=200,
        )
        result = check.check_provider("example", CFG, "sk-test")
        assert result.status == check.STATUS_UNKNOWN
        assert result.message == "key valid, limit info unavailable"

    @responses.activate
    def test_429_is_limited_with_reset(self) -> None:
        responses.get(
            "https://api.example.com/v1/models",
            status=429,
            headers={"retry-after": "45"},
        )
        result = check.check_provider("example", CFG, "sk-test")
        assert result.status == check.STATUS_LIMITED
        assert result.is_limited
        assert result.reset_seconds == 45
        assert "resets in" in result.message

    @responses.activate
    def test_429_without_reset(self) -> None:
        responses.get(
            "https://api.example.com/v1/models",
            status=429,
        )
        result = check.check_provider("example", CFG, "sk-test")
        assert result.status == check.STATUS_LIMITED
        assert result.reset_seconds is None

    @pytest.mark.parametrize("status_code", [401, 403])
    @responses.activate
    def test_auth_failure_is_error(self, status_code: int) -> None:
        responses.get(
            "https://api.example.com/v1/models",
            json={"error": "nope"},
            status=status_code,
        )
        result = check.check_provider("example", CFG, "sk-bad")
        assert result.status == check.STATUS_ERROR
        assert result.is_error
        assert str(status_code) in result.message
        assert "auth failed" in result.message

    @responses.activate
    def test_other_4xx_is_error(self) -> None:
        responses.get(
            "https://api.example.com/v1/models",
            json={"error": "broken"},
            status=500,
        )
        result = check.check_provider("example", CFG, "sk-test")
        assert result.status == check.STATUS_ERROR
        assert "http 500" in result.message

    def test_network_exception_is_error(self) -> None:
        # No @responses.activate — `responses` raises if an unexpected
        # request goes out, so we patch requests.get directly.
        with patch(
            "ratewatch.check.requests.get",
            side_effect=requests.ConnectionError("boom"),
        ):
            result = check.check_provider("example", CFG, "sk-test")
        assert result.status == check.STATUS_ERROR
        assert "network error" in result.message

    def test_default_endpoint_used_when_test_endpoint_missing(self) -> None:
        cfg = {**CFG}
        cfg.pop("test_endpoint")
        with patch(
            "ratewatch.check.requests.get",
            side_effect=requests.ConnectionError("boom"),
        ) as get_mock:
            check.check_provider("example", cfg, "sk-test")
        # /v1/  (base_url stripped, missing endpoint coerced to "/")
        args, _ = get_mock.call_args
        assert args[0].endswith("/v1/")


# ===========================================================================
# check_provider_live (POST chat-completion probe)
# ===========================================================================

class TestCheckProviderLive:
    def test_returns_error_when_chat_model_missing(self) -> None:
        cfg = {**CFG}  # no chat_model
        result = check.check_provider_live("example", cfg, "sk-test")
        assert result.status == check.STATUS_ERROR
        assert "no chat_model" in result.message

    @responses.activate
    def test_openai_chat_success(self) -> None:
        cfg = {
            **CFG,
            "chat_model": "gpt-4o-mini",
            # No chat_endpoint → defaults to /chat/completions
        }
        responses.post(
            "https://api.example.com/v1/chat/completions",
            json={"choices": []},
            status=200,
            headers={
                "x-ratelimit-remaining-requests": "80",
                "x-ratelimit-limit-requests": "100",
            },
        )
        result = check.check_provider_live("example", cfg, "sk-test")
        assert result.status == check.STATUS_OK
        assert result.remaining == 80

    @responses.activate
    def test_anthropic_chat_success(self) -> None:
        cfg = {
            **CFG,
            "base_url": "https://api.anthropic.com",
            "auth_header_format": "x-api-key: {key}",
            "test_endpoint": "/v1/models",
            "extra_headers": {"anthropic-version": "2023-06-01"},
            "chat_model": "claude-haiku-4-5",
            "chat_endpoint": "/v1/messages",
            "chat_format": "anthropic",
        }
        responses.post(
            "https://api.anthropic.com/v1/messages",
            json={"content": []},
            status=200,
            headers={
                "anthropic-ratelimit-requests-remaining": "100",
                "anthropic-ratelimit-requests-limit": "200",
            },
        )
        result = check.check_provider_live("anthropic", cfg, "sk-test")
        assert result.status == check.STATUS_OK
        assert result.remaining == 100
        assert result.limit == 200

    @responses.activate
    def test_gemini_chat_substitutes_model_in_url(self) -> None:
        cfg = {
            **CFG,
            "base_url": "https://generativelanguage.googleapis.com",
            "auth_header_format": "x-goog-api-key: {key}",
            "test_endpoint": "/v1beta/models",
            "chat_model": "gemini-2.0-flash-lite",
            "chat_endpoint": "/v1beta/models/{model}:generateContent",
            "chat_format": "gemini",
        }
        responses.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            "gemini-2.0-flash-lite:generateContent",
            json={"candidates": []},
            status=200,
            headers={"x-ratelimit-remaining": "90"},
        )
        result = check.check_provider_live("gemini", cfg, "AIza-test")
        assert result.status == check.STATUS_OK
        assert result.remaining == 90

    @responses.activate
    def test_429_in_live_mode(self) -> None:
        cfg = {**CFG, "chat_model": "gpt-4o-mini"}
        responses.post(
            "https://api.example.com/v1/chat/completions",
            status=429,
            headers={"retry-after": "120"},
        )
        result = check.check_provider_live("example", cfg, "sk-test")
        assert result.status == check.STATUS_LIMITED
        assert result.reset_seconds == 120

    @responses.activate
    def test_auth_failure_in_live_mode(self) -> None:
        cfg = {**CFG, "chat_model": "gpt-4o-mini"}
        responses.post(
            "https://api.example.com/v1/chat/completions",
            json={"error": "bad key"},
            status=401,
        )
        result = check.check_provider_live("example", cfg, "sk-bad")
        assert result.status == check.STATUS_ERROR
        assert "auth failed" in result.message

    @responses.activate
    def test_no_rate_limit_headers_in_live_mode(self) -> None:
        cfg = {**CFG, "chat_model": "gpt-4o-mini"}
        responses.post(
            "https://api.example.com/v1/chat/completions",
            json={"choices": []},
            status=200,
        )
        result = check.check_provider_live("example", cfg, "sk-test")
        assert result.status == check.STATUS_UNKNOWN

    def test_network_exception_in_live_mode(self) -> None:
        cfg = {**CFG, "chat_model": "gpt-4o-mini"}
        with patch(
            "ratewatch.check.requests.post",
            side_effect=requests.Timeout("slow"),
        ):
            result = check.check_provider_live("example", cfg, "sk-test")
        assert result.status == check.STATUS_ERROR
        assert "network error" in result.message
