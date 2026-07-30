"""Tests for ratewatch.config — add/remove/list/reset + mask_key.

All tests use the `isolated_config_dir` fixture from conftest.py so they
never read or write the real on-disk config file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ratewatch import config


# A minimal valid cfg dict for add_key(); tests that need extra fields
# build on top of this.
def _cfg(**overrides) -> dict:
    base = {
        "base_url": "https://api.example.com/v1",
        "auth_header_format": "Authorization: Bearer {key}",
        "test_endpoint": "/models",
    }
    base.update(overrides)
    return base


# --- add_key ---------------------------------------------------------------

class TestAddKey:
    def test_add_first_provider(self, isolated_config_dir: Path) -> None:
        result = config.add_key("openai", "sk-test-1234abcd", _cfg())
        assert result == "added"

        on_disk = config.get_providers()
        assert "openai" in on_disk
        assert on_disk["openai"]["key"] == "sk-test-1234abcd"
        assert on_disk["openai"]["base_url"] == "https://api.example.com/v1"

    def test_add_overwrite_when_confirmed(
        self, isolated_config_dir: Path
    ) -> None:
        config.add_key("openai", "old-key-1111", _cfg())
        result = config.add_key("openai", "new-key-2222", _cfg(), overwrite=True)
        assert result == "overwritten"
        assert config.get_provider("openai")["key"] == "new-key-2222"

    def test_add_refuses_overwrite_by_default(
        self, isolated_config_dir: Path
    ) -> None:
        config.add_key("openai", "old-key-1111", _cfg())
        with pytest.raises(ValueError, match="already configured"):
            config.add_key("openai", "new-key-2222", _cfg())
        # Original key preserved.
        assert config.get_provider("openai")["key"] == "old-key-1111"

    def test_add_persists_extra_fields(self, isolated_config_dir: Path) -> None:
        cfg = _cfg(chat_model="gpt-4o-mini", validation_endpoint="/v1/chat")
        config.add_key("openai", "sk-test-1234abcd", cfg)
        assert config.get_provider("openai")["chat_model"] == "gpt-4o-mini"
        assert config.get_provider("openai")["validation_endpoint"] == "/v1/chat"

    @pytest.mark.parametrize("bad_name", ["", "   "])
    def test_add_rejects_blank_provider_name(
        self, isolated_config_dir: Path, bad_name: str
    ) -> None:
        with pytest.raises(ValueError, match="provider name"):
            config.add_key(bad_name, "sk-real-key-1234", _cfg())

    @pytest.mark.parametrize("bad_key", ["", "   "])
    def test_add_rejects_blank_key(
        self, isolated_config_dir: Path, bad_key: str
    ) -> None:
        with pytest.raises(ValueError, match="key cannot be empty"):
            config.add_key("openai", bad_key, _cfg())

    def test_add_rejects_missing_required_field(
        self, isolated_config_dir: Path
    ) -> None:
        bad = {"base_url": "https://x", "auth_header_format": "Bearer {key}"}
        # no test_endpoint
        with pytest.raises(ValueError, match="test_endpoint"):
            config.add_key("openai", "sk-real-key-1234", bad)


# --- remove_key ------------------------------------------------------------

class TestRemoveKey:
    def test_remove_existing_returns_true(
        self, isolated_config_dir: Path
    ) -> None:
        config.add_key("openai", "sk-test-1234abcd", _cfg())
        assert config.remove_key("openai") is True
        assert "openai" not in config.get_providers()

    def test_remove_missing_returns_false(
        self, isolated_config_dir: Path
    ) -> None:
        assert config.remove_key("nope") is False

    def test_last_remove_clears_providers_section(
        self, isolated_config_dir: Path
    ) -> None:
        config.add_key("openai", "sk-test-1234abcd", _cfg())
        config.remove_key("openai")
        on_disk = config._read()
        # Providers section should be gone (not just empty) so the TOML
        # file stays compact.
        assert "providers" not in on_disk


# --- list_keys / _mask_key -------------------------------------------------

class TestListKeysAndMask:
    def test_list_keys_masks_using_helper(self, isolated_config_dir: Path) -> None:
        config.add_key("openai", "sk-verylong-secret-key-1234", _cfg())
        config.add_key("anthropic", "ant-payload-5678", _cfg())
        rows = config.list_keys()
        assert rows["openai"] == "●●●●●●1234"
        assert rows["anthropic"] == "●●●●●●5678"

    def test_list_keys_empty_when_nothing_configured(
        self, isolated_config_dir: Path
    ) -> None:
        assert config.list_keys() == {}

    @pytest.mark.parametrize(
        "key, expected",
        [
            ("sk-verylong-secret-1234", "●●●●●●1234"),
            ("abcd", "●●●●"),
            ("abc", "●●●●"),
            ("", ""),
        ],
    )
    def test_mask_key(self, key: str, expected: str) -> None:
        assert config.mask_key(key) == expected


# --- reset -----------------------------------------------------------------

class TestReset:
    def test_reset_deletes_config_file(
        self, isolated_config_dir: Path
    ) -> None:
        config.add_key("openai", "sk-test-1234abcd", _cfg())
        cfg_file = isolated_config_dir / config.CONFIG_FILE_NAME
        assert cfg_file.exists()
        assert config.reset() is True
        assert not cfg_file.exists()

    def test_reset_returns_false_when_absent(
        self, isolated_config_dir: Path
    ) -> None:
        assert config.reset() is False


# --- has_provider / get_provider smoke tests -------------------------------

class TestLookup:
    def test_has_provider(self, isolated_config_dir: Path) -> None:
        assert not config.has_provider("openai")
        config.add_key("openai", "sk-test-1234abcd", _cfg())
        assert config.has_provider("openai")

    def test_get_provider_returns_none_for_missing(self, isolated_config_dir: Path) -> None:
        assert config.get_provider("ghost") is None
