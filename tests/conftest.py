"""Shared test fixtures.

`isolated_config_dir` redirects `ratewatch.config.config_dir()` to a tmp
directory so tests never touch the real user config file.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ratewatch import config


@pytest.fixture
def isolated_config_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config, "config_dir", lambda: tmp_path)
    return tmp_path
