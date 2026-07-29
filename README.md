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

## Commands

### `ratewatch providers`

List all built-in provider presets and whether each is configured.

```bash
ratewatch providers
```

### `ratewatch add <provider>`

Add a provider. When a preset is known, only the API key is prompted. Otherwise
you'll be asked for the base URL, auth header format, and test endpoint too.

```bash
# interactive (prompted for key)
ratewatch add openai

# non-interactive via --key flag
ratewatch add groq --key $GROQ_KEY

# non-interactive via environment variable
export RATEWATCH_KEY=sk-abc123
ratewatch add anthropic
```

Precedence: `--key` flag > `RATEWATCH_KEY` env var > interactive prompt.

### `ratewatch check [<provider>]`

Check rate-limit status. Defaults to all configured providers. Exits non-zero
if any provider is rate-limited.

```bash
# probe a single provider
ratewatch check groq

# probe everything configured
ratewatch check

# live mode — sends a real chat request for accurate numbers
ratewatch check groq --live

# JSON output for scripting
ratewatch check --json

# custom timeout (seconds; default 10 for cheap, 15 for live)
ratewatch check groq --timeout 5.0

# quiet mode — suppresses non-essential stderr (e.g. live-mode warning)
ratewatch check --live --quiet

# combine flags
ratewatch check --live --json --quiet
```

### `ratewatch list`

Show configured providers with masked keys.

```bash
ratewatch list
```

### `ratewatch export`

Print the full provider config as JSON with every key field masked. Safe for
backup or scripting — pipe to a file.

```bash
ratewatch export > backup.json
```

### `ratewatch remove <provider>`

Remove a configured provider.

```bash
ratewatch remove openai
```

### `ratewatch reset`

Delete the entire config file.

```bash
ratewatch reset
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

