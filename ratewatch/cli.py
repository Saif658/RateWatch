"""Click CLI for ratewatch."""

from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor
from functools import partial

import click

from . import __version__, check, config, providers


# ---------------------------------------------------------------------------
# Top-level group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option(__version__, prog_name="ratewatch")
def main() -> None:
    """Check rate-limit status for LLM API providers."""


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------

@main.command()
@click.argument("provider", required=False)
@click.option(
    "--key",
    default=None,
    help=(
        "API key. If omitted, checks the RATEWATCH_KEY environment variable, "
        "then prompts interactively."
    ),
)
def add(provider: str | None, key: str | None) -> None:
    """Add a provider key (configures a built-in preset or prompts for custom)."""
    if provider is None:
        preset_names = providers.list_preset_names()
        if not preset_names:
            click.echo("no built-in providers.")
            return
        
        click.echo("Available providers:")
        width = max(len(p) for p in preset_names)
        for name in preset_names:
            click.echo(f"  {name.ljust(width)}")
        
        click.echo("")
        click.echo("Usage: ratewatch add <provider>")
        click.echo("Providers not listed here can still be added manually — ratewatch will prompt for base URL, auth header, and test endpoint.")
        return
    
    if config.has_provider(provider):
        if not click.confirm(f"{provider!r} is already configured, overwrite?", default=False):
            click.echo("aborted.", err=True)
            sys.exit(1)

    preset = providers.get_preset(provider)

    if preset is not None:
        click.echo(f"using preset for {provider}: {preset['base_url']}")
        base_url = preset["base_url"]
        auth_header_format = preset["auth_header_format"]
        test_endpoint = preset["test_endpoint"]
        extra_headers = preset.get("extra_headers")
    else:
        click.echo(f"no preset for {provider!r}; defining a custom provider.")
        base_url = click.prompt("base URL (e.g. https://api.example.com/v1)")
        auth_header_format = click.prompt(
            'auth header format (e.g. "Authorization: Bearer {key}")'
        )
        test_endpoint = click.prompt('test endpoint (path, e.g. "/models")')
        extra_headers = None

    if key is None:
        key = os.environ.get("RATEWATCH_KEY")
    if key is None:
        key = click.prompt(f"API key for {provider}", hide_input=True)
    if not key:
        click.echo("empty key not allowed", err=True)
        sys.exit(2)

    # Start from the preset wholesale so chat_model / validation_endpoint /
    # any future field flows through without us listing them explicitly.
    # For custom providers, preset is None so cfg starts empty.
    cfg = dict(preset) if preset is not None else {}
    cfg["base_url"] = base_url
    cfg["auth_header_format"] = auth_header_format
    cfg["test_endpoint"] = test_endpoint
    if extra_headers:
        cfg["extra_headers"] = extra_headers

    click.echo("validating with one test request...")
    # When a preset declares validation_endpoint, the cheap GET against
    # test_endpoint is not enough (some providers return 200 for bogus
    # keys), so we POST to validation_endpoint instead, mirroring the
    # --live probe in shape.
    if cfg.get("validation_endpoint"):
        result = check.check_provider_live(provider, cfg, key)
    else:
        result = check.check_provider(provider, cfg, key)
    if result.status == check.STATUS_ERROR:
        click.echo(f"validation failed: {result.message}", err=True)
        sys.exit(2)
    if result.status == check.STATUS_LIMITED:
        click.echo(
            f"warning: key is already rate-limited. saved anyway.\n  detail: {result.message}",
            err=True,
        )

    config.add_key(provider, key, cfg, overwrite=True)
    click.echo(f"saved {provider}.")


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------

@main.command()
@click.argument("provider")
def remove(provider: str) -> None:
    """Remove a configured provider."""
    if not config.has_provider(provider):
        click.echo(f"{provider!r} is not configured.", err=True)
        sys.exit(1)
    if not click.confirm(f"remove {provider}?", default=False):
        click.echo("aborted.", err=True)
        sys.exit(1)
    config.remove_key(provider)
    click.echo(f"removed {provider}.")


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

@main.command("list")
def list_cmd() -> None:
    """List configured providers (masked keys)."""
    rows = config.list_keys()
    if not rows:
        click.echo("no providers configured. run `ratewatch add <provider>` to add one.")
        return
    width = max(len(name) for name in rows)
    for name in sorted(rows):
        click.echo(f"{name.ljust(width)}  {rows[name]}")


# ---------------------------------------------------------------------------
# providers
# ---------------------------------------------------------------------------

@main.command("providers")
def providers_cmd() -> None:
    """List all built-in provider presets and whether each is configured."""
    configured = set(config.list_keys())
    preset_names = providers.list_preset_names()

    if not preset_names:
        click.echo("no built-in providers.")
        return

    width = max(len(p) for p in preset_names)
    for name in preset_names:
        status = "configured" if name in configured else "not added"
        click.echo(f"{name.ljust(width)}  {status}")

    click.echo("")
    click.echo(
        "Run `ratewatch add <provider>` to configure one. "
        "Providers not listed here can still be added manually — "
        "ratewatch will prompt for base URL, auth header, and test endpoint."
    )


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

@main.command()
def reset() -> None:
    """Delete the entire config file."""
    if not click.confirm("delete the entire ratewatch config?", default=False):
        click.echo("aborted.", err=True)
        sys.exit(1)
    if config.reset():
        click.echo("config deleted.")
    else:
        click.echo("nothing to delete.")


# ---------------------------------------------------------------------------
# check
# ---------------------------------------------------------------------------

@main.command()
@click.argument("provider", required=False)
@click.option(
    "--live",
    is_flag=True,
    help=(
        "Send a real chat-completion request to each provider instead of the "
        "cheap /models probe. Useful when the lightweight endpoint doesn't "
        "expose rate-limit headers."
    ),
)
@click.option(
    "--json",
    "as_json",
    is_flag=True,
    help=(
        "Print results as a JSON array (one object per provider) instead of "
        "the rich text table. Useful for scripting. Exit codes are unchanged."
    ),
)
@click.option(
    "--timeout",
    default=None,
    type=click.FloatRange(min=0, min_open=True),
    help=(
        "Timeout in seconds for each probe request "
        "(default: 10 for cheap probe, 15 for --live probe)."
    ),
)
@click.option(
    "-q",
    "--quiet",
    is_flag=True,
    help="Suppress non-essential stderr chatter (e.g. live-mode warning).",
)
def check_cmd(provider: str | None, live: bool, as_json: bool, timeout: float | None, quiet: bool) -> None:
    """Check rate-limit status. Defaults to all configured providers."""
    if provider is not None:
        cfg = config.get_provider(provider)
        if cfg is None:
            click.echo(f"{provider!r} is not configured.", err=True)
            sys.exit(1)
        entries = [(provider, cfg, cfg["key"])]
    else:
        all_cfg = config.get_providers()
        if not all_cfg:
            click.echo("no providers configured.")
            sys.exit(1)
        entries = sorted(all_cfg.items(), key=lambda kv: kv[0])
        entries = [(name, cfg, cfg["key"]) for name, cfg in entries]

    if live and not quiet:
        click.echo(
            "live mode sends a real request to each provider "
            "and may use a small amount of your quota.",
            err=True,
        )
        probe_fn = check.check_provider_live
    else:
        probe_fn = check.check_provider
    if timeout is not None:
        probe_fn = partial(probe_fn, timeout=timeout)

    # Each probe is a blocking HTTP call, so run them concurrently in
    # threads to parallelize the I/O. executor.map() returns results in
    # input order, so the output stays sorted by provider name regardless
    # of completion order.
    with ThreadPoolExecutor(max_workers=len(entries)) as executor:
        results = list(executor.map(probe_fn, *zip(*entries)))

    if as_json:
        payload = [
            {
                "provider": r.provider,
                "status": r.status,
                "remaining": r.remaining,
                "limit": r.limit,
                "reset_seconds": r.reset_seconds,
                "message": r.message,
            }
            for r in results
        ]
        click.echo(json.dumps(payload, indent=2))
    else:
        check.print_results(results)

    if any(r.is_limited for r in results):
        sys.exit(1)


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

@main.command()
def export() -> None:
    """Print full config as JSON with masked keys (safe for backup/scripting)."""
    providers_cfg = config.get_providers()
    if not providers_cfg:
        click.echo("no providers configured.")
        return

    out = {}
    for name, cfg in providers_cfg.items():
        entry = dict(cfg)
        entry["key"] = config.mask_key(cfg["key"])
        out[name] = entry

    click.echo(json.dumps(out, indent=2))
