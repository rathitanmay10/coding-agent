# How to use `coding-agent`

A practical walkthrough. For the reference list of flags, see `README.md`.

---

## 1. One-time setup

```bash
git clone <this-repo> ~/code/coding-agent
cd ~/code/coding-agent
uv sync --extra dev          # creates .venv, installs pydantic-ai + httpx
uv run pytest                # sanity check: should print "45 passed"
```

Add a shell alias so you can call it from any project:

```bash
# ~/.zshrc
alias ca='uv run --project ~/code/coding-agent coding-agent'
```

Reload your shell. Now `ca` works anywhere.

---

## 2. Choose a backend

| | Ollama | OpenRouter |
|---|---|---|
| Where it runs | Your machine | Cloud (model-agnostic gateway) |
| Cost | $0 | Pay-per-token, one key for many models |
| Setup | `brew install ollama && ollama pull <model>` | Get key at <https://openrouter.ai/keys> |
| Best for | Privacy, offline, free experimentation | Frontier models (Claude, GPT-4o, etc.) |
| Tool-call quality | Iffy on <7B models | Reliable on most models |

---

## 3. Run with Ollama (local)

### Start the daemon

```bash
ollama serve            # in another terminal
ollama pull qwen2.5-coder:7b
```

### Launch agent

Interactive picker:

```bash
cd ~/my-project
ca
```

```
Providers:
  1. ollama (local)
  2. openrouter (cloud)
Pick [1-2]: 1
Available Ollama models:
  1. gemma4:e4b
  2. qwen2.5-coder:7b
Pick [1-2]: 2

coding-agent — provider: ollama, model: qwen2.5-coder:7b
locked to: /Users/you/my-project  (cannot escape this directory)
Type /help for commands.

logging session to: .coding-agent/logs/session-20260101-104530.jsonl

>
```

Skip both pickers:

```bash
ca --provider ollama --model qwen2.5-coder:7b
```

Remote Ollama:

```bash
ca --provider ollama --host http://192.168.1.50:11434
```

Resume your last session (recap of prior turns is seeded into history):

```bash
ca --resume                 # most recent session
ca --resume .coding-agent/logs/session-20260101-104530.jsonl
```

---

## 4. Run with OpenRouter (cloud)

### Get a key

1. Sign up at <https://openrouter.ai/>
2. Load credit ($5 lasts a long time for Sonnet/4o-mini)
3. Create a key at <https://openrouter.ai/keys>

### Pass the key (3 options, in priority order)

**Option A — `.env` file** (recommended)

In your project root:

```
# .env
OPENROUTER_API_KEY=sk-or-v1-...
```

Then:

```bash
ca --provider openrouter --model anthropic/claude-sonnet-4.5
```

**Option B — environment variable**

```bash
export OPENROUTER_API_KEY=sk-or-v1-...
ca --provider openrouter --model openai/gpt-4o
```

**Option C — CLI flag**

```bash
ca --provider openrouter --model openai/gpt-4o-mini --api-key sk-or-v1-...
```

**Option D — interactive prompt**

If none of the above is set:

```
OpenRouter API key (input hidden): ********
```

### Picking a model

If you don't pass `--model`, the picker shows common slugs and accepts any other:

```
Common OpenRouter models:
  1. z-ai/glm-4.5-air:free
  2. openrouter/free
  Or type any other slug from https://openrouter.ai/models
Model: 1
```

Full slug list: <https://openrouter.ai/models>

---

## 5. A real session

```
> Look at this repo and tell me what it does
  → list_dir({})
    ↳ ['README.md', 'pyproject.toml', 'src/', 'tests/']
  → read_file({"path":"README.md"})
    ↳ 1	# my-project ...

[turn 1] in=4200 out=180 req=2 t=8.41s | session total: in=4200 out=180 req=2

This repo is a Python data-pipeline that ...

> Add a docstring to the main() function in src/cli.py
  → read_file({"path":"src/cli.py"})
    ↳ 1	import argparse ...
  → edit_file({"path":"src/cli.py","old":"def main():\n    args = parse_args()","new":"def main():\n    \"\"\"Entry point: parse args and run pipeline.\"\"\"\n    args = parse_args()"})

─── edit_file ───
--- src/cli.py
+++ src/cli.py
@@ -10,1 +10,2 @@
 def main():
+    """Entry point: parse args and run pipeline."""
     args = parse_args()
Approve? [y/N/a] y
    ↳ Edited src/cli.py

[turn 2] in=5100 out=240 req=2 t=9.02s | session total: in=9300 out=420 req=4

Added docstring to `main()` in src/cli.py.

> /exit
session total: in=9300 out=420 req=4 turns=2
```

---

## 6. Approval prompts

Every `write_file`, `edit_file`, `multi_edit`, `delete_file`, `move_file`, and
`run_bash` call prompts:

```
─── edit_file ───
--- foo.py
+++ foo.py
@@ -3,1 +3,1 @@
-def old(): pass
+def new(): pass
Approve? [y/N/a]
```

- `y` / `yes` → execute this one call
- `a` / `always` → execute, and **auto-approve every later call to this tool** for the rest of the session (kills approval fatigue without going full `--yolo`)
- anything else / `n` / Enter → deny. Tool returns `"User denied: edit_file"`. Agent sees that and can ask what to do.
- `Ctrl-D` → denies and ends the run.

`a` is per-tool and per-session: approving `run_bash` with `a` won't auto-approve
`delete_file`, and the allowlist resets when you quit.

### Denylist (always refused)

`run_bash` refuses obviously destructive commands **before** the prompt — even
under `--yolo`:

```
> rm everything
  → run_bash({"command":"rm -rf /"})
    ↳ Error: refused: command matches destructive denylist pattern (...)
```

Patterns: `rm -rf /` or `~`, fork bombs, `dd of=/dev/...`, `mkfs`, raw-disk redirects.

**Skip the y/N prompts** (dangerous, for trusted local work):

```bash
ca --yolo
```

Banner warns:

```
⚠  --yolo: destructive tools will NOT prompt for approval.
```

(The denylist still applies under `--yolo`.)

---

## 7. REPL commands

| Command | Effect |
|---|---|
| `<text>` | Send a turn to the agent |
| `/help` | List all REPL commands |
| `/exit`, `/quit`, Ctrl-D | Quit, print session totals |
| `/clear` | Reset conversation history (keep agent + provider) |
| `/compact` | Summarize prior turns into one recap message; shrinks context to fit small windows |
| `/model` | Re-pick provider + model from scratch (resets history) |
| `/stats` | Print running token + turn totals + log path |

`Ctrl-C` mid-turn cancels just that turn (returns to `>`); at the empty prompt it quits.

`/compact` is local text summarization (no extra model call) — useful when a long
session approaches a small model's context limit.

---

## 8. Logs

Every session writes one JSONL file:

```
<your-project>/.coding-agent/logs/session-<YYYYMMDD-HHMMSS>.jsonl
```

Add to `.gitignore`:

```
.coding-agent/
```

One JSON object per line. Useful queries:

```bash
# Replay a session
cat .coding-agent/logs/session-*.jsonl | jq .

# Total tokens used today
cat .coding-agent/logs/session-$(date +%Y%m%d)*.jsonl \
  | jq -s 'map(select(.type=="turn")) | {in: (map(.usage.input_tokens) | add), out: (map(.usage.output_tokens) | add)}'

# Every tool call I made this session
jq -c 'select(.type=="turn") | .tool_calls[]' .coding-agent/logs/session-<id>.jsonl
```

Record shape:

```json
{
  "type": "turn",
  "ts": 1779986560.467,
  "turn": 1,
  "user": "list files",
  "tool_calls": [{"name": "list_dir", "args": "{}"}],
  "output": "Here are the files...",
  "error": null,
  "duration_s": 2.34,
  "usage": {"input_tokens": 1621, "output_tokens": 159, "requests": 2}
}
```

---

## 9. Sandbox

The agent is locked to the directory you launched it from. Every tool resolves paths against that root via `Path.is_relative_to`. Attempts to escape (`../../etc/passwd`, absolute paths outside cwd, symlinks pointing out) return:

```
Error: Path escapes working directory: ../../etc/passwd
```

There is **no** `--cwd` flag. The launch dir is the only knob.

`run_bash` runs with `shell=True` and inherits your env — the sandbox is path-based, not capability-based. Approve every command unless you're using `--yolo`.

---

## 10. Tips & gotchas

- **Small Ollama models flake on tool calls.** `gemma4:e2b` and many 7B models hallucinate the JSON. Stick to `qwen2.5-coder:7b` or larger for local work; switch to OpenRouter for cheap-and-good.
- **First Ollama turn is slow.** The model has to be loaded into VRAM. Subsequent turns are fast until Ollama unloads it (default 5 min idle).
- **`edit_file` is exact-match string replace.** If the model passes a `old` that isn't a unique substring, the tool errors out and the model retries. Encourage it to read the file first.
- **Binary files** are detected and rejected by `read_file` — no UnicodeDecodeError noise.
- **Concurrent edits.** `edit_file` records the file's mtime before approval and refuses to write if the file changed during the prompt. If you edit the same file in your IDE while the agent is asking, the write is aborted.
- **`grep` uses ripgrep if installed.** Falls back to pure-Python on systems without `rg`. Both paths skip `.git`, `.venv`, `node_modules`, `__pycache__`, `dist`, `build`, etc. — no junk matches. `brew install ripgrep` recommended.
- **Cost watching.** `/stats` shows running totals mid-session. End-of-session totals print on `/exit` or Ctrl-D.
- **Output streams live.** Assistant text appears token-by-token; tool calls print to stderr as they fire. Long answers don't block on a blank screen.
- **Transient errors retry automatically.** Dropped connections and HTTP 429/5xx back off and retry a few times before the turn fails — handy on flaky networks or rate-limited OpenRouter keys.
- **Project context on boot.** The agent starts with a shallow dir tree + the head of `CLAUDE.md`/`README.md`, so it can answer "what does this repo do" without grepping around first.
- **`multi_edit` for batched changes.** One file, several `{old, new}` edits applied atomically — if any `old` isn't a unique match, the whole batch aborts (no partial write) and you keep one approval prompt instead of N.
- **Stuck in a long session?** Run `/compact` to fold history into a recap and free up context, or `--resume` next time to pick up where you left off.

---

## 11. Troubleshooting

**`Could not reach Ollama at http://localhost:11434`**
→ Run `ollama serve` in another terminal.

**`No models found at ...`**
→ `ollama pull qwen2.5-coder:7b` (or any other).

**`401 User not found` from OpenRouter**
→ Wrong/expired API key. Get a fresh one at <https://openrouter.ai/keys>.

**`402 insufficient credits` from OpenRouter**
→ Top up at <https://openrouter.ai/credits>.

**Agent calls a tool with garbage args / hallucinates a path**
→ Model too small. Use `/model` to switch to a stronger one, or try a different provider.

**Agent edits the wrong location**
→ Run `git diff` after the session. Tool calls are logged in JSONL — you can always replay. Use `/clear` to drop bad history and start fresh in the same session.

**`Error: command timed out after 30s` from grep**
→ Pathological regex on a large tree. Narrow `path=` or `glob=` arguments.
