# coding-agent

CLI coding harness powered by [Pydantic AI](https://ai.pydantic.dev/). Two backends:

- **Ollama** — fully local, no API key
- **OpenRouter** — cloud, one API key buys access to most frontier models

Drives file edits, shell commands, and code search against your local project.

## Requirements

- Python 3.10+
- For Ollama: [Ollama](https://ollama.com/) running locally (`ollama serve`) + at least one model pulled
- For OpenRouter: an API key from <https://openrouter.ai/keys>
- Optional: `ripgrep` (`rg`) on PATH for faster `grep` tool

## Install

Uses [uv](https://github.com/astral-sh/uv) for env + deps.

```bash
cd coding-agent
uv sync --extra dev
```

## Run

```bash
# Fully interactive: pick provider, then model:
uv run coding-agent

# Ollama, specific model:
uv run coding-agent --provider ollama --model qwen2.5-coder:7b

# OpenRouter (key from env or .env):
uv run coding-agent --provider openrouter --model anthropic/claude-sonnet-4.5

# OpenRouter, explicit key:
uv run coding-agent --provider openrouter --model openai/gpt-4o --api-key sk-or-v1-...

# Skip approval prompts (dangerous):
uv run coding-agent --yolo

# Remote/non-default Ollama host:
uv run coding-agent --provider ollama --host http://192.168.1.50:11434
```

## .env file

If a `.env` exists in the launch directory, it is loaded at startup. Use it for `OPENROUTER_API_KEY`:

```
OPENROUTER_API_KEY=sk-or-v1-...
```

CLI `--api-key` beats env beats `.env` beats interactive prompt.

## REPL commands

| Command | Effect |
|---|---|
| `/exit`, `/quit`, Ctrl-D | Quit (prints session totals) |
| `/clear` | Reset conversation history |
| `/model` | Re-pick model (resets history) |
| `/stats` | Show running token + turn totals |

## Sandbox

Agent is locked to the directory you launch from. Every tool resolves paths against that root; anything escaping (`../../etc/passwd`) is rejected. No `--cwd` override flag.

## Session metrics + logs

- Each turn prints `[turn N] in=X out=Y req=Z t=Ts | session total: ...` to stderr.
- `/stats` prints the running totals on demand.
- JSONL log written to `./.coding-agent/logs/session-<YYYYMMDD-HHMMSS>.jsonl` with one record per turn: `{user, tool_calls, output, usage, duration_s, error}`.
- Add `.coding-agent/` to your `.gitignore`.

## Tools the agent can call

- **read_file**, **list_dir**, **glob_files**, **grep** — read-only, no prompt
- **write_file**, **edit_file**, **run_bash** — prompts y/N before each call (unless `--yolo`)

All paths are confined to the directory you launch from.

## Model picks

Smaller models (≤7B) sometimes fumble tool-call JSON. If the agent hallucinates calls or stalls, try `qwen2.5-coder:7b` or larger.

## Tests

```bash
uv run pytest
```
