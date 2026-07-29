# ratewatch

A small CLI that probes your LLM API providers and tells you how close you are
to a rate limit — before you hit it.

```
groq:       ✅ 142/500 requests remaining (resets in 12m)
openrouter: ⚠️  18/100 requests remaining
gemini:     ❌ rate limited, resets in 4m
custom_x:   ℹ️  key valid, limit info unavailable
```

## Install

Requires Python 3.11+.

```bash
pip install -e .
```

## Contributing / running tests

Run the test suite straight from a checkout — no install needed:

```bash
pip install -r requirements-dev.txt
pytest
```

## Usage

```bash
# list all built-in provider presets and whether each is configured
ratewatch providers

# add a provider (prompted for key only when a preset is known)
ratewatch add openai
ratewatch add anthropic

# add a provider with a key non-interactively (flag, or RATEWATCH_KEY env var)
ratewatch add groq --key $GROQ_KEY

# probe a single provider
ratewatch check groq

# probe with a real request for accurate numbers (uses a tiny amount of quota)
ratewatch check groq --live

# probe with a custom timeout (seconds; default 10 for cheap, 15 for --live)
ratewatch check groq --timeout 5.0

# probe everything configured
ratewatch check

# emit a JSON array of results (one object per provider) for scripting
ratewatch check --json
```

`ratewatch check` exits with a non-zero status if any provider is rate-limited,
so it's scriptable. Pass `--json` to emit a JSON array (one object per provider,
with `provider`, `status`, `remaining`, `limit`, `reset_seconds`, and `message`
fields) instead of the colored table — the exit codes are unchanged:

```bash
ratewatch check && echo "every provider is healthy"
ratewatch check --json | jq 'map(select(.status == "limited"))'
```

Other commands:

```bash
ratewatch list     # show providers with masked keys
ratewatch export   # full config as JSON with masked keys (for backup/scripting)
ratewatch remove <provider>
ratewatch reset    # delete the entire config file
```

## Supported out of the box

OpenAI, Anthropic, NVIDIA NIM, OpenRouter, Gemini, DeepSeek, Mistral,
Mistral Codestral, OpenCode Zen, OpenCode Go, Wafer, Kimi, Cerebras,
Groq, Fireworks, Z.ai.

A preset is just a base URL, an auth header format, and a cheap probe
endpoint (usually `/models`). When a preset's URL or header drifts, the
probe still runs — it just falls through to "key valid, limit info
unavailable" instead of crashing.

Not every provider exposes live rate-limit data on every endpoint. Some
providers (e.g. NVIDIA NIM) don't expose remaining-quota info at all —
you'll see "key valid, limit info unavailable" until you actually hit a
429. Use `--live` mode for a more accurate read on providers that
support it, but note this uses a small amount of real quota since it
sends an actual request.

## Custom providers

If your provider isn't in the preset list, `ratewatch add` will ask for:

- **base URL** — e.g. `https://api.example.com/v1`
- **auth header format** — e.g. `Authorization: Bearer {key}` or
  `x-api-key: {key}`. `{key}` is replaced with your API key at probe time.
- **test endpoint** — a cheap GET path, typically `/models`.
- **API key**

On first save, ratewatch makes one probe request to validate the key
before persisting the config.

## Security

Keys are stored in plaintext at `~/.config/ratewatch/config.toml`
(`%APPDATA%\ratewatch\config.toml` on Windows). The file is created with
mode `0o600` where the platform supports it. Keys never leave your machine
— every probe is issued from your own process. `ratewatch list` only ever
prints a masked key (`●●●●●●abcd`).

If that's not acceptable, don't use this tool.

## Header coverage

Different providers publish rate-limit metadata under different header
names. ratewatch scans for all of these (case-insensitive):

- `x-ratelimit-*-requests|tokens`, `x-ratelimit-*-reset`
- `ratelimit-remaining|limit|reset`
- `x-rate-limit-*`
- `anthropic-ratelimit-*-remaining|limit|reset`
- `retry-after`

Reset values are parsed as integer seconds, OpenAI-style durations
(`1m23s`), ISO timestamps, or HTTP-date. If none are present, the key is
reported valid and the limit is listed as unknown.

## Exit codes

- `0` — every checked provider is not rate-limited
- `1` — at least one provider is rate-limited (or a non-rate-limit error)
- `2` — misconfiguration (missing arg, empty key, validation failure, etc.)

`--json` changes only the output format; the exit codes above are unchanged.

