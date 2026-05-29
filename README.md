# coding-agent

CLI coding harness powered by [Pydantic AI](https://ai.pydantic.dev/). Two backends:

- **Ollama** — fully local, no API key
- **OpenRouter** — cloud, one API key buys access to most frontier models

Drives file edits, shell commands, and code search against your local project.

Features: live token **streaming**, gitignore-aware search, project-context priming
on boot, per-tool **approval allowlist**, a destructive-command denylist,
transient-error retry, Ctrl-C cancels the current turn (not the app), `/compact`
history summarization, and `--resume` to continue a past session.

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

# Resume the most recent session (or pass a session-*.jsonl path):
uv run coding-agent --resume          # = --resume latest
uv run coding-agent --resume .coding-agent/logs/session-20260101-104530.jsonl
```

`--resume` seeds the conversation with a recap of the prior session's turns so the
model has context to continue from.

## .env file

If a `.env` exists in the launch directory, it is loaded at startup. Use it for `OPENROUTER_API_KEY`:

```
OPENROUTER_API_KEY=sk-or-v1-...
```

CLI `--api-key` beats env beats `.env` beats interactive prompt.

## REPL commands

| Command | Effect |
|---|---|
| `/help` | List all REPL commands |
| `/exit`, `/quit`, Ctrl-D | Quit (prints session totals) |
| `/clear` | Reset conversation history |
| `/compact` | Summarize old turns into one recap; shrinks context |
| `/model` | Re-pick model (resets history) |
| `/stats` | Show running token + turn totals |

`Ctrl-C` during a turn cancels that turn and returns to the prompt — it does **not**
quit the app. `Ctrl-C`/`Ctrl-D` at the empty prompt quits.

## Sandbox

Agent is locked to the directory you launch from. Every tool resolves paths against that root; anything escaping (`../../etc/passwd`) is rejected. No `--cwd` override flag.

## Session metrics + logs

- Each turn prints `[turn N] in=X out=Y req=Z t=Ts | session total: ...` to stderr.
- `/stats` prints the running totals on demand.
- JSONL log written to `./.coding-agent/logs/session-<YYYYMMDD-HHMMSS>.jsonl` with one record per turn: `{user, tool_calls, output, usage, duration_s, error}`.
- Add `.coding-agent/` to your `.gitignore`.

## Tools the agent can call

- **read_file**, **list_dir**, **glob_files**, **grep** — read-only, no prompt. `glob_files`/`grep` skip `.git`, `.venv`, `node_modules`, `__pycache__`, etc. (ripgrep respects your `.gitignore`).
- **write_file**, **edit_file**, **multi_edit**, **delete_file**, **move_file**, **run_bash** — prompt before each call (unless `--yolo`).

All paths are confined to the directory you launch from.

### Approval prompt

Destructive tools prompt `Approve? [y/N/a]`:

- `y` / `yes` → run this one call
- `a` / `always` → run, and auto-approve every later call to **this tool** for the rest of the session
- anything else → deny (tool returns `"User denied: <tool>"`)

`run_bash` additionally **refuses outright** (before any prompt) commands matching a
destructive denylist — `rm -rf /` / `~`, fork bombs, `dd of=/dev/...`, `mkfs`,
raw-disk redirects — even under `--yolo`.

## Resilience

- **Streaming** — assistant text prints token-by-token as it arrives.
- **Retry** — transient errors (connection drops, HTTP 429/5xx) retry with exponential backoff before failing the turn.
- **Cancel** — `Ctrl-C` aborts the in-flight turn and returns to the prompt.
- **Project context** — on boot the agent is primed with a shallow directory tree and the head of `CLAUDE.md`/`README.md`, so it isn't blind to the project on turn one.

## Model picks

Smaller models (≤7B) sometimes fumble tool-call JSON. If the agent hallucinates calls or stalls, try `qwen2.5-coder:7b` or larger.

## Tests

```bash
uv run pytest
```
