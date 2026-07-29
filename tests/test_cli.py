"""CLI tests for `ratewatch check` -- the --json flag and the concurrent
probe path.

All tests use the `isolated_config_dir` fixture (see conftest.py) so they
never touch the real user config, and they patch the probe functions in
ratewatch.check so no real HTTP is made.
"""

from __future__ import annotations

import json
import threading
import time

import pytest
from click.testing import CliRunner

from ratewatch import check, cli, config


# A minimal provider cfg for config.add_key(); deep state lives on disk
# under isolated_config_dir, so we hand add_key a fresh dict each time.
CFG = {
    "base_url": "https://api.example.com/v1",
    "auth_header_format": "Authorization: Bearer {key}",
    "test_endpoint": "/models",
}


def _add_provider(name: str) -> None:
    """Persist a configured provider under the isolated config dir."""
    config.add_key(name, f"sk-{name}-1234abcd", dict(CFG))


# ===========================================================================
# --json output
# ===========================================================================

class TestJsonOutput:
    def test_emits_array_with_expected_keys(self, isolated_config_dir, monkeypatch):
        _add_provider("groq")
        _add_provider("openai")

        def fake_probe(name, cfg, key, **kwargs):
            return check.CheckResult(
                provider=name,
                status=check.STATUS_OK,
                remaining=60,
                limit=100,
                reset_seconds=30,
                message="ok",
            )

        monkeypatch.setattr(check, "check_provider", fake_probe)

        result = CliRunner().invoke(cli.main, ["check", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) == 2
        for obj in data:
            assert set(obj.keys()) == {
                "provider",
                "status",
                "remaining",
                "limit",
                "reset_seconds",
                "message",
            }
        # raw_headers is intentionally excluded from the JSON payload.
        # Order follows the sorted entry order (groq, then openai).
        assert [o["provider"] for o in data] == ["groq", "openai"]
        assert data[0]["remaining"] == 60
        assert data[0]["reset_seconds"] == 30

    def test_single_provider(self, isolated_config_dir, monkeypatch):
        _add_provider("groq")

        def fake_probe(name, cfg, key, **kwargs):
            return check.CheckResult(
                provider=name, status=check.STATUS_OK, remaining=10, message="ok"
            )

        monkeypatch.setattr(check, "check_provider", fake_probe)

        result = CliRunner().invoke(cli.main, ["check", "groq", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["provider"] == "groq"

    def test_zero_exit_when_all_ok(self, isolated_config_dir, monkeypatch):
        _add_provider("groq")

        monkeypatch.setattr(
            check,
            "check_provider",
            lambda name, cfg, key, **kw: check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            ),
        )

        result = CliRunner().invoke(cli.main, ["check", "--json"])
        assert result.exit_code == 0

    def test_nonzero_exit_when_any_limited(self, isolated_config_dir, monkeypatch):
        _add_provider("groq")

        def fake_probe(name, cfg, key, **kwargs):
            return check.CheckResult(
                provider=name,
                status=check.STATUS_LIMITED,
                reset_seconds=45,
                message="rate limited",
            )

        monkeypatch.setattr(check, "check_provider", fake_probe)

        result = CliRunner().invoke(cli.main, ["check", "--json"])
        # Exit code logic is unchanged by --json: limited -> 1.
        assert result.exit_code == 1
        data = json.loads(result.output)
        assert data[0]["status"] == "limited"
        assert data[0]["reset_seconds"] == 45

    def test_default_output_is_not_json(self, isolated_config_dir, monkeypatch):
        # Without --json we must fall through to the rich table, so stdout
        # should NOT be parseable as a JSON array.
        _add_provider("groq")
        monkeypatch.setattr(
            check,
            "check_provider",
            lambda name, cfg, key, **kw: check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            ),
        )

        result = CliRunner().invoke(cli.main, ["check"])
        assert result.exit_code == 0
        with pytest.raises(json.JSONDecodeError):
            json.loads(result.output)


# ===========================================================================
# Concurrent probe path
# ===========================================================================

class TestConcurrentCheck:
    def test_probes_run_in_parallel(self, isolated_config_dir, monkeypatch):
        # A barrier sized to the provider count only releases once that many
        # probes are in flight simultaneously. A sequential impl would let the
        # first probe block forever (until the barrier times out), so passing
        # this test proves the probes actually run concurrently.
        names = ["alpha", "bravo", "charlie"]
        for n in names:
            _add_provider(n)

        barrier = threading.Barrier(len(names), timeout=3.0)
        calls = []

        def fake_probe(name, cfg, key, **kwargs):
            calls.append(name)
            barrier.wait()  # blocks until all `len(names)` probes are running
            return check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            )

        monkeypatch.setattr(check, "check_provider", fake_probe)

        result = CliRunner().invoke(cli.main, ["check"])
        assert result.exception is None
        assert result.exit_code == 0
        assert sorted(calls) == sorted(names)

    def test_order_preserved_under_out_of_order_completion(
        self, isolated_config_dir, monkeypatch
    ):
        # Insert in non-sorted order; entries sort to alpha, bravo, charlie.
        # Make the first-sorted provider ("alpha") finish last and the last
        # ("charlie") finish first. The output must still come out in the
        # sorted entry order -- this guards against an as_completed-style
        # scramble in the threaded path.
        for n in ["charlie", "alpha", "bravo"]:
            _add_provider(n)

        delays = {"alpha": 0.15, "bravo": 0.08, "charlie": 0.01}

        def fake_probe(name, cfg, key, **kwargs):
            time.sleep(delays[name])
            return check.CheckResult(
                provider=name, status=check.STATUS_OK, message=name
            )

        monkeypatch.setattr(check, "check_provider", fake_probe)

        result = CliRunner().invoke(cli.main, ["check", "--json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert [o["provider"] for o in data] == ["alpha", "bravo", "charlie"]

    def test_live_flag_routes_to_live_probe(self, isolated_config_dir, monkeypatch):
        _add_provider("groq")
        live_calls = []

        def fake_live(name, cfg, key, **kwargs):
            live_calls.append(name)
            return check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            )

        monkeypatch.setattr(check, "check_provider_live", fake_live)
        # The cheap probe must not be used when --live is passed.
        monkeypatch.setattr(
            check,
            "check_provider",
            lambda *a, **k: pytest.fail("expected --live to use check_provider_live"),
        )

        result = CliRunner().invoke(cli.main, ["check", "--live"])
        assert result.exit_code == 0
        assert live_calls == ["groq"]


# ===========================================================================
# add --key and RATEWATCH_KEY env var
# ===========================================================================

class TestAddKeyOption:
    def test_flag_provided(self, isolated_config_dir, monkeypatch):
        monkeypatch.setattr(
            check,
            "check_provider",
            lambda name, cfg, key, **kw: check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            ),
        )
        result = CliRunner().invoke(
            cli.main, ["add", "groq", "--key", "sk-groq-abc123"]
        )
        assert result.exit_code == 0
        assert "saved groq." in result.output
        # Verify the correct key was stored
        stored = config.get_provider("groq")
        assert stored is not None
        assert stored["key"] == "sk-groq-abc123"

    def test_env_var_fallback(self, isolated_config_dir, monkeypatch):
        monkeypatch.setattr(
            check,
            "check_provider",
            lambda name, cfg, key, **kw: check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            ),
        )
        monkeypatch.setenv("RATEWATCH_KEY", "sk-groq-from-env")
        result = CliRunner().invoke(cli.main, ["add", "groq"])
        assert result.exit_code == 0
        assert "saved groq." in result.output
        stored = config.get_provider("groq")
        assert stored is not None
        assert stored["key"] == "sk-groq-from-env"

    def test_flag_overrides_env_var(self, isolated_config_dir, monkeypatch):
        monkeypatch.setattr(
            check,
            "check_provider",
            lambda name, cfg, key, **kw: check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            ),
        )
        monkeypatch.setenv("RATEWATCH_KEY", "sk-env-var")
        result = CliRunner().invoke(
            cli.main, ["add", "groq", "--key", "sk-flag-wins"]
        )
        assert result.exit_code == 0
        assert "saved groq." in result.output
        stored = config.get_provider("groq")
        assert stored is not None
        assert stored["key"] == "sk-flag-wins"

    def test_empty_flag_errors(self, isolated_config_dir, monkeypatch):
        result = CliRunner().invoke(
            cli.main, ["add", "groq", "--key", ""]
        )
        assert result.exit_code == 2
        assert "empty key" in result.output


# ===========================================================================
# check --timeout
# ===========================================================================

class TestCheckTimeout:
    def test_timeout_passed_to_probe(self, isolated_config_dir, monkeypatch):
        _add_provider("groq")
        captured_kwargs = {}

        def fake_probe(name, cfg, key, **kwargs):
            captured_kwargs.update(kwargs)
            return check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            )

        monkeypatch.setattr(check, "check_provider", fake_probe)
        result = CliRunner().invoke(cli.main, ["check", "--timeout", "7.5"])
        assert result.exit_code == 0
        assert captured_kwargs.get("timeout") == 7.5

    def test_timeout_passed_to_live_probe(self, isolated_config_dir, monkeypatch):
        _add_provider("groq")
        captured_kwargs = {}

        def fake_live(name, cfg, key, **kwargs):
            captured_kwargs.update(kwargs)
            return check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            )

        monkeypatch.setattr(check, "check_provider_live", fake_live)
        monkeypatch.setattr(
            check,
            "check_provider",
            lambda *a, **k: pytest.fail("expected --live to use check_provider_live"),
        )
        result = CliRunner().invoke(cli.main, ["check", "--live", "--timeout", "7.5"])
        assert result.exit_code == 0
        assert captured_kwargs.get("timeout") == 7.5

    def test_invalid_timeout_errors(self, isolated_config_dir):
        _add_provider("groq")
        result = CliRunner().invoke(cli.main, ["check", "--timeout", "0"])
        assert result.exit_code == 2

    def test_negative_timeout_errors(self, isolated_config_dir):
        _add_provider("groq")
        result = CliRunner().invoke(cli.main, ["check", "--timeout", "-1"])
        assert result.exit_code == 2

    def test_no_timeout_uses_default(self, isolated_config_dir, monkeypatch):
        _add_provider("groq")
        captured_kwargs = {}

        def fake_probe(name, cfg, key, **kwargs):
            captured_kwargs.update(kwargs)
            return check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            )

        monkeypatch.setattr(check, "check_provider", fake_probe)
        result = CliRunner().invoke(cli.main, ["check"])
        assert result.exit_code == 0
        # timeout should not be forwarded when not specified
        assert "timeout" not in captured_kwargs


# ===========================================================================
# check --quiet
# ===========================================================================

class TestCheckQuiet:
    def test_quiet_suppresses_live_warning_on_stderr(
        self, isolated_config_dir, monkeypatch
    ):
        _add_provider("groq")
        monkeypatch.setattr(
            check,
            "check_provider_live",
            lambda name, cfg, key, **kw: check.CheckResult(
                provider=name, status=check.STATUS_OK, message="ok"
            ),
        )
        result = CliRunner().invoke(cli.main, ["check", "--live", "--json", "--quiet"])
        assert result.exit_code == 0
        assert result.stderr == ""


# ===========================================================================
# export
# ===========================================================================

class TestExport:
    def test_keys_are_masked_in_output(self, isolated_config_dir):
        _add_provider("groq")
        _add_provider("openai")
        result = CliRunner().invoke(cli.main, ["export"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert set(data.keys()) == {"groq", "openai"}
        for entry in data.values():
            # key must be masked: starts with ● and ends with last 4 chars
            assert entry["key"].startswith("●")
            assert entry["key"].endswith("abcd")

    def test_export_json_is_parseable(self, isolated_config_dir):
        _add_provider("groq")
        result = CliRunner().invoke(cli.main, ["export"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["groq"]["base_url"] == "https://api.example.com/v1"
        assert data["groq"]["auth_header_format"] == "Authorization: Bearer {key}"
        assert data["groq"]["test_endpoint"] == "/models"

    def test_no_providers(self, isolated_config_dir):
        result = CliRunner().invoke(cli.main, ["export"])
        assert result.exit_code == 0
        assert result.output.strip() == "no providers configured."
