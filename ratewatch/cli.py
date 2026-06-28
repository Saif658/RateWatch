"""Click CLI for ratewatch."""

from __future__ import annotations

import sys

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
@click.argument("provider")
def add(provider: str) -> None:
    """Add a provider key (configures a built-in preset or prompts for custom)."""
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

    key = click.prompt(f"API key for {provider}", hide_input=True, confirmation_prompt=False)
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
def check_cmd(provider: str | None, live: bool) -> None:
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

    from . import check as check_mod
    if live:
        click.echo(
            "live mode sends a real request to each provider "
            "and may use a small amount of your quota.",
            err=True,
        )
        probe_fn = check_mod.check_provider_live
    else:
        probe_fn = check_mod.check_provider

    results = [probe_fn(name, cfg, key) for name, cfg, key in entries]
    check_mod.print_results(results)

    if any(r.is_limited for r in results):
        sys.exit(1)
