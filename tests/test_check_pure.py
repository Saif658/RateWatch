"""Tests for the pure helpers in ratewatch.check — no HTTP, no I/O."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import pytest

from ratewatch import check


# --- _parse_reset ----------------------------------------------------------

class TestParseReset:
    @pytest.mark.parametrize(
        "value, expected",
        [
            ("0", 0),
            ("30", 30),
            ("3600", 3600),
            ("  120  ", 120),  # whitespace tolerated
        ],
    )
    def test_pure_seconds_int(self, value: str, expected: int) -> None:
        assert check._parse_reset(value) == expected

    def test_pure_seconds_rejects_non_digits(self) -> None:
        # "30s" must NOT hit the "pure number" branch — only `isdigit()` strings
        # should; the duration branch should handle it.
        assert check._parse_reset("30s") == 30

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("30s", 30),
            ("2m", 120),
            ("2m30s", 150),
            ("1h", 3600),
            ("1h30m", 5400),
            ("1h30m15s", 5415),
            ("45.5s", 45),  # float seconds get int-truncated
            ("1m0.5s", 60),  # floats in any position
        ],
    )
    def test_duration_strings(self, value: str, expected: int) -> None:
        assert check._parse_reset(value) == expected

    def test_iso_timestamp_future_with_z(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=1)
        value = future.strftime("%Y-%m-%dT%H:%M:%SZ")
        result = check._parse_reset(value)
        # Allow a few seconds of skew between strftime and the function's
        # own datetime.now() call.
        assert result is not None
        assert 3590 <= result <= 3610

    def test_iso_timestamp_future_with_offset(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=30)
        value = future.strftime("%Y-%m-%dT%H:%M:%S+00:00")
        result = check._parse_reset(value)
        assert result is not None
        assert 1790 <= result <= 1810

    def test_iso_timestamp_naive_treated_as_utc(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(minutes=10)
        value = future.strftime("%Y-%m-%dT%H:%M:%S")  # no tz info
        result = check._parse_reset(value)
        assert result is not None
        assert 590 <= result <= 610

    def test_iso_timestamp_in_past_clamps_to_zero(self) -> None:
        past = datetime.now(timezone.utc) - timedelta(hours=2)
        value = past.strftime("%Y-%m-%dT%H:%M:%SZ")
        assert check._parse_reset(value) == 0

    def test_http_date_rfc1123(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=3)
        # RFC 1123 with %Z → emits "GMT" when tzinfo=utc
        value = future.strftime("%a, %d %b %Y %H:%M:%S GMT")
        result = check._parse_reset(value)
        assert result is not None
        assert 10790 <= result <= 10810

    def test_http_date_rfc850(self) -> None:
        future = datetime.now(timezone.utc) + timedelta(hours=2)
        value = future.strftime("%A, %d-%b-%y %H:%M:%S GMT")
        result = check._parse_reset(value)
        assert result is not None
        assert 7190 <= result <= 7210

    @pytest.mark.parametrize("garbage", ["", "not a date", "garbage", "1y0m0d"])
    def test_unparseable_returns_none(self, garbage: str) -> None:
        # "1y0m0d" has no recognized unit → duration regex fails, ISO fails,
        # HTTP date fails → None.
        assert check._parse_reset(garbage) is None


# --- _first_numeric --------------------------------------------------------

class TestFirstNumeric:
    def test_returns_first_match_as_int(self) -> None:
        # Headers are stored lowercased; helper expects that.
        headers = {
            "x-ratelimit-remaining-requests": "42",
            "x-ratelimit-limit": "100",
        }
        assert (
            check._first_numeric(headers, check._REMAINING_HEADERS) == 42
        )

    def test_strips_openai_style_suffix(self) -> None:
        headers = {"x-ratelimit-remaining-requests": "12.7s"}
        assert (
            check._first_numeric(headers, check._REMAINING_HEADERS) == 12
        )

    def test_returns_none_when_no_match(self) -> None:
        assert check._first_numeric({}, check._REMAINING_HEADERS) is None

    def test_skips_unparseable_and_keeps_looking(self) -> None:
        # First header has garbage, second is valid → second wins.
        headers = {
            "x-ratelimit-remaining-requests": "garbage",
            "x-ratelimit-remaining": "7",
        }
        assert (
            check._first_numeric(headers, check._REMAINING_HEADERS) == 7
        )


# --- _classify_from_remaining ----------------------------------------------

class TestClassifyFromRemaining:
    def test_zero_is_limited(self) -> None:
        assert (
            check._classify_from_remaining(0, 100) == check.STATUS_LIMITED
        )

    def test_below_half_limit_is_warn(self) -> None:
        # 40/100 < 50% → warn (also < 50 → warn; both branches agree here)
        assert check._classify_from_remaining(40, 100) == check.STATUS_WARN

    def test_below_fifty_is_warn_even_without_limit(self) -> None:
        assert check._classify_from_remaining(10, None) == check.STATUS_WARN

    def test_above_half_limit_is_ok(self) -> None:
        assert check._classify_from_remaining(60, 100) == check.STATUS_OK

    def test_unknown_remaining_is_ok(self) -> None:
        # No remaining info → we don't have evidence of being limited.
        assert check._classify_from_remaining(None, 100) == check.STATUS_OK

    def test_above_fifty_without_limit_is_ok(self) -> None:
        assert check._classify_from_remaining(999, None) == check.STATUS_OK
