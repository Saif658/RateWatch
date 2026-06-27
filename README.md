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

```bash
pip install -e .
```

Requires Python 3.10+.

## Usage

```bash
# add a provider (prompted for key only when a preset is known)
ratewatch add openai
ratewatch add anthropic

# probe a single provider
ratewatch check groq

# probe everything configured
ratewatch check
```

`ratewatch check` exits with a non-zero status if any provider is rate-limited,
so it's scriptable:

```bash
ratewatch check && echo "every provider is healthy"
```

Other commands:

```bash
ratewatch list     # show providers with masked keys
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

## License

MIT.
