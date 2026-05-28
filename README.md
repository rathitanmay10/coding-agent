# coding-agent

Local CLI coding harness powered by [Pydantic AI](https://ai.pydantic.dev/) + [Ollama](https://ollama.com/).
Drives file edits, shell commands, and code search against your local project — no cloud calls, no API keys.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) running locally (`ollama serve`)
- At least one model pulled (e.g. `ollama pull qwen2.5-coder:7b`)
- Optional: `ripgrep` (`rg`) on PATH for faster `grep` tool

## Install

Uses [uv](https://github.com/astral-sh/uv) for env + deps.

```bash
cd coding-agent
uv sync --extra dev
```

## Run

```bash
# Pick model interactively from `ollama list`:
uv run coding-agent

# Or pass directly:
uv run coding-agent --model qwen2.5-coder:7b

# Skip approval prompts (dangerous):
uv run coding-agent --yolo

# Remote/non-default Ollama host:
uv run coding-agent --host http://192.168.1.50:11434
```

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
