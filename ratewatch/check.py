"""Rate-limit probe loop.

One generic check_provider(provider_config, key) does all the actual work:
build URL, send request, scan headers, classify status. check_all wraps it
to produce colored output for every configured provider.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable

import requests
from rich.console import Console
from rich.text import Text

# Header keys we'll consider for rate-limit metadata.
# Lower-case; matched against header names with case-insensitive equality.
_REMAINING_HEADERS = (
    "x-ratelimit-remaining-requests",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-remaining",
    "ratelimit-remaining",
    "x-rate-limit-remaining",
    "anthropic-ratelimit-requests-remaining",
    "anthropic-ratelimit-tokens-remaining",
)
_LIMIT_HEADERS = (
    "x-ratelimit-limit-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-limit",
    "ratelimit-limit",
    "x-rate-limit-limit",
    "anthropic-ratelimit-requests-limit",
    "anthropic-ratelimit-tokens-limit",
)
_RESET_HEADERS = (
    "x-ratelimit-reset-requests",
    "x-ratelimit-reset-tokens",
    "x-ratelimit-reset",
    "ratelimit-reset",
    "x-rate-limit-reset",
    "anthropic-ratelimit-requests-reset",
    "anthropic-ratelimit-tokens-reset",
    "retry-after",
)

# Status string constants returned to the CLI for icon/color picking.
STATUS_OK = "ok"
STATUS_WARN = "warn"
STATUS_LIMITED = "limited"
STATUS_UNKNOWN = "unknown"
STATUS_ERROR = "error"


@dataclass
class CheckResult:
    provider: str
    status: str
    remaining: int | None = None
    limit: int | None = None
    reset_seconds: int | None = None
    message: str = ""
    raw_headers: dict[str, str] = field(default_factory=dict)

    @property
    def is_limited(self) -> bool:
        return self.status == STATUS_LIMITED

    @property
    def is_error(self) -> bool:
        return self.status == STATUS_ERROR


# ---------------------------------------------------------------------------
# One probe
# ---------------------------------------------------------------------------

def check_provider(name: str, config: dict, key: str, *, timeout: float = 10.0) -> CheckResult:
    """Send a single probe and classify the response."""
    url = _join_url(config["base_url"], config.get("test_endpoint", "/"))
    headers = _build_headers(config, key)

    try:
        resp = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        return CheckResult(
            provider=name,
            status=STATUS_ERROR,
            message=f"network error: {e.__class__.__name__}",
        )

    raw = {k.lower(): v for k, v in resp.headers.items()}

    if resp.status_code == 429:
        return _classify_limited(name, raw)

    if resp.status_code in (401, 403):
        return CheckResult(
            provider=name,
            status=STATUS_ERROR,
            message=f"auth failed ({resp.status_code})",
        )

    if resp.status_code >= 400:
        return CheckResult(
            provider=name,
            status=STATUS_ERROR,
            message=f"http {resp.status_code}",
        )

    # Success path: parse rate-limit headers.
    remaining = _first_numeric(raw, _REMAINING_HEADERS)
    limit = _first_numeric(raw, _LIMIT_HEADERS)
    reset_sec = _first_reset_seconds(raw, _RESET_HEADERS)

    if remaining is None and limit is None and reset_sec is None:
        return CheckResult(
            provider=name,
            status=STATUS_UNKNOWN,
            message="key valid, limit info unavailable",
            raw_headers=raw,
        )

    status = _classify_from_remaining(remaining, limit)
    msg = _format_summary(remaining, limit, reset_sec)
    return CheckResult(
        provider=name,
        status=status,
        remaining=remaining,
        limit=limit,
        reset_seconds=reset_sec,
        message=msg,
        raw_headers=raw,
    )


def _classify_limited(name: str, raw_headers: dict[str, str]) -> CheckResult:
    reset_sec = _first_reset_seconds(raw_headers, _RESET_HEADERS)
    msg = f"rate limited, resets in {_humanize_duration(reset_sec)}" if reset_sec else "rate limited"
    return CheckResult(
        provider=name,
        status=STATUS_LIMITED,
        reset_seconds=reset_sec,
        message=msg,
        raw_headers=raw_headers,
    )


def _classify_from_remaining(remaining: int | None, limit: int | None) -> str:
    if remaining is not None and remaining <= 0:
        return STATUS_LIMITED
    if (
        remaining is not None
        and limit is not None
        and limit > 0
        and remaining < limit / 2
    ):
        return STATUS_WARN
    if remaining is not None and remaining < 50:
        return STATUS_WARN
    return STATUS_OK


def _format_summary(remaining: int | None, limit: int | None, reset_sec: int | None) -> str:
    # Group remaining + limit together when both are present, like "12/100 requests remaining".
    if remaining is not None and limit is not None:
        head = f"{remaining}/{limit} requests remaining"
    elif remaining is not None:
        head = f"{remaining} requests remaining"
    elif limit is not None:
        head = f"{limit} requests available"
    else:
        head = ""

    tail = ""
    if reset_sec is not None:
        tail = f" (resets in {_humanize_duration(reset_sec)})"
    elif not head:
        tail = "key valid, limit info unavailable"
    return head + tail


# ---------------------------------------------------------------------------
# All providers
# ---------------------------------------------------------------------------

def check_all(entries: Iterable[tuple[str, dict, str]]) -> list[CheckResult]:
    """Probe every configured provider.

    entries is an iterable of (name, config, key) tuples.
    """
    results = []
    for name, cfg, key in entries:
        results.append(check_provider(name, cfg, key))
    return results


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _join_url(base: str, endpoint: str) -> str:
    base = base.rstrip("/")
    endpoint = endpoint if endpoint.startswith("/") else "/" + endpoint
    return base + endpoint


def _build_headers(config: dict, key: str) -> dict[str, str]:
    out: dict[str, str] = {}
    fmt = config.get("auth_header_format") or "Authorization: Bearer {key}"
    header_name, _, value = fmt.partition(":")
    value = value.strip().replace("{key}", key)
    out[header_name.strip()] = value
    for k, v in (config.get("extra_headers") or {}).items():
        out[k] = v
    return out


def _first_numeric(headers: dict[str, str], names: tuple[str, ...]) -> int | None:
    # Headers are looked up case-insensitively (we lowercased them above).
    for n in names:
        v = headers.get(n)
        if v is None:
            continue
        # OpenAI-style: "1.2s", "0.3s", etc.
        m = re.match(r"[\s]*([0-9]+(?:\.[0-9]+)?)", v)
        if m:
            try:
                return int(float(m.group(1)))
            except ValueError:
                continue
    return None


def _first_reset_seconds(headers: dict[str, str], names: tuple[str, ...]) -> int | None:
    for n in names:
        v = headers.get(n)
        if v is None:
            continue
        sec = _parse_reset(v)
        if sec is not None:
            return sec
    return None


def _parse_reset(value: str) -> int | None:
    value = value.strip()
    if not value:
        return None
    # Pure number (seconds).
    if value.isdigit():
        return int(value)
    # Duration string like "1m23s", "2h", "30s", "1h30m".
    m = re.fullmatch(r"(?:(\d+)h)?(?:(\d+)m)?(?:(\d+(?:\.\d+)?)s)?", value)
    if m and (m.group(1) or m.group(2) or m.group(3)):
        h = int(m.group(1) or 0)
        mi = int(m.group(2) or 0)
        s = float(m.group(3) or 0)
        return int(h * 3600 + mi * 60 + s)
    # Anthropic-style ISO timestamp in the future.
    try:
        ts = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        delta = (ts - datetime.now(timezone.utc)).total_seconds()
        return max(0, int(delta))
    except ValueError:
        pass
    # RFC 1123 / 850 HTTP date.
    for fmt in ("%a, %d %b %Y %H:%M:%S %Z", "%A, %d-%b-%y %H:%M:%S %Z"):
        try:
            ts = datetime.strptime(value, fmt)
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            delta = (ts - datetime.now(timezone.utc)).total_seconds()
            return max(0, int(delta))
        except ValueError:
            continue
    return None


def _humanize_duration(seconds: int | None) -> str:
    if seconds is None:
        return "?"
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds / 60.0
    if minutes < 90:
        return f"{int(round(minutes))}m"
    hours = minutes / 60.0
    if hours < 36:
        return f"{int(round(hours))}h"
    days = hours / 24.0
    return f"{int(round(days))}d"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

_STATUS_ICONS: dict[str, tuple[str, str]] = {
    STATUS_OK: ("✅", "green"),
    STATUS_WARN: ("⚠️", "yellow"),
    STATUS_LIMITED: ("❌", "red"),
    STATUS_UNKNOWN: ("ℹ️", "dim"),
    STATUS_ERROR: ("🔴", "red"),
}


def print_results(results: list[CheckResult]) -> None:
    """Render a list of CheckResults as colored, aligned lines."""
    if not results:
        return
    width = max(len(r.provider) for r in results)
    console = Console()
    for r in results:
        icon, style = _STATUS_ICONS.get(r.status, ("?", ""))
        line = Text()
        line.append(f"{r.provider}:".ljust(width + 1), style="bold")
        line.append(f"{icon} ", style=style)
        line.append(r.message or "(no detail)", style=style)
        console.print(line)
