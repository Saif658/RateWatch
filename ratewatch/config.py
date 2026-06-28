"""Configuration storage for ratewatch.

Keys are stored in plaintext in a TOML file under the user config dir
(see README for the security note). File permissions are tightened to
0o600 wherever the platform supports it.
"""

from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path

import tomli_w
from platformdirs import user_config_dir

CONFIG_DIR_NAME = "ratewatch"
CONFIG_FILE_NAME = "config.toml"


def config_dir() -> Path:
    """Return the platform-specific config directory, creating it if needed."""
    path = Path(user_config_dir(CONFIG_DIR_NAME, CONFIG_DIR_NAME))
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return config_dir() / CONFIG_FILE_NAME


def _read() -> dict:
    """Read the config file. Returns an empty dict if it doesn't exist."""
    p = config_path()
    if not p.exists():
        return {}
    with p.open("rb") as f:
        return tomllib.load(f)


def _write(data: dict) -> None:
    """Write the config dict to disk with 0o600 permissions."""
    p = config_path()
    with p.open("wb") as f:
        tomli_w.dump(data, f)
    # Best-effort: tighten permissions on POSIX. Windows ignores mode bits.
    try:
        os.chmod(p, 0o600)
    except (OSError, NotImplementedError):
        pass


def get_providers() -> dict:
    """Return the providers section of the config (empty dict if missing)."""
    return _read().get("providers", {})


def has_provider(provider: str) -> bool:
    return provider in get_providers()


def get_provider(provider: str) -> dict | None:
    providers = get_providers()
    return providers.get(provider)


# --- mutations --------------------------------------------------------------

def add_key(
    provider: str,
    key: str,
    cfg: dict,
    *,
    overwrite: bool = False,
) -> str:
    """Save a provider + key to the config.

    cfg must contain base_url, auth_header_format, and test_endpoint at
    minimum. Every other field in cfg (chat_model, validation_endpoint,
    extra_headers, anything new added later) is persisted verbatim.

    Returns "added" or "overwritten". Raises ValueError on bad input.
    Network validation is done by the caller (cli.py) before this is
    invoked.
    """
    if not provider or not provider.strip():
        raise ValueError("provider name cannot be empty")
    if not key or not key.strip():
        raise ValueError("key cannot be empty")

    base_url = cfg.get("base_url")
    auth_header_format = cfg.get("auth_header_format")
    test_endpoint = cfg.get("test_endpoint")
    if not base_url or not auth_header_format or not test_endpoint:
        raise ValueError(
            "cfg must include base_url, auth_header_format, and test_endpoint"
        )

    data = _read()
    providers = data.setdefault("providers", {})

    if provider in providers and not overwrite:
        raise ValueError(f"provider {provider!r} already configured")

    # Wholesale copy so future preset fields (chat_model, validation_endpoint,
    # anything new) propagate to disk without code changes here.
    entry = dict(cfg)
    entry["key"] = key

    existed = provider in providers
    providers[provider] = entry
    _write(data)
    return "overwritten" if existed else "added"


def remove_key(provider: str) -> bool:
    """Remove a provider. Returns True if anything was removed."""
    data = _read()
    providers = data.setdefault("providers", {})
    if provider not in providers:
        return False
    del providers[provider]
    if not providers:
        del data["providers"]
    _write(data)
    return True


def list_keys() -> dict[str, str]:
    """Return a {provider: masked_key} mapping. Never exposes full keys."""
    providers = get_providers()
    return {name: _mask_key(p["key"]) for name, p in providers.items()}


def reset() -> bool:
    """Delete the config file entirely. Returns True if a file was deleted."""
    p = config_path()
    if p.exists():
        p.unlink()
        return True
    return False


# --- helpers ----------------------------------------------------------------

def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 4:
        return "●●●●"
    return "●●●●●●" + key[-4:]
