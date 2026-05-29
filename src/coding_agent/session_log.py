"""Per-session JSONL logger + token accumulator."""

from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TurnRecord:
    user: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    output: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    requests: int = 0
    error: str | None = None
    duration_s: float = 0.0


class SessionLogger:
    """Append one JSON object per turn to a session file; track running token totals."""

    def __init__(self, cwd: Path, model: str) -> None:
        self.cwd = cwd
        self.model = model
        ts = time.strftime("%Y%m%d-%H%M%S")
        log_dir = cwd / ".coding-agent" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        self.path = log_dir / f"session-{ts}.jsonl"
        self.total_input = 0
        self.total_output = 0
        self.total_requests = 0
        self.turn_count = 0
        self._write(
            {
                "type": "session_start",
                "ts": time.time(),
                "model": model,
                "cwd": str(cwd),
            }
        )

    def _write(self, obj: dict[str, Any]) -> None:
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(obj, default=str) + "\n")
        except OSError as e:
            print(f"[session_log] write failed: {e}", file=sys.stderr)

    def log_turn(self, rec: TurnRecord) -> None:
        self.turn_count += 1
        self.total_input += rec.input_tokens
        self.total_output += rec.output_tokens
        self.total_requests += rec.requests
        self._write(
            {
                "type": "turn",
                "ts": time.time(),
                "turn": self.turn_count,
                "user": rec.user,
                "tool_calls": rec.tool_calls,
                "output": rec.output,
                "error": rec.error,
                "duration_s": round(rec.duration_s, 3),
                "usage": {
                    "input_tokens": rec.input_tokens,
                    "output_tokens": rec.output_tokens,
                    "requests": rec.requests,
                },
            }
        )

    def metrics_line(self, last: TurnRecord) -> str:
        return (
            f"[turn {self.turn_count}] "
            f"in={last.input_tokens} out={last.output_tokens} "
            f"req={last.requests} t={last.duration_s:.2f}s | "
            f"session total: in={self.total_input} out={self.total_output} "
            f"req={self.total_requests}"
        )


def load_session(path: Path) -> list[TurnRecord]:
    """Read a session JSONL file back into TurnRecord objects (turn lines only).

    Skips the session_start line and any malformed/non-turn lines.
    Used by --resume to rebuild conversation history.
    """
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    records: list[TurnRecord] = []
    for line in lines:
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("type") != "turn":
            continue
        usage = obj.get("usage") or {}
        records.append(
            TurnRecord(
                user=obj.get("user", ""),
                tool_calls=obj.get("tool_calls") or [],
                output=obj.get("output", ""),
                error=obj.get("error"),
                duration_s=obj.get("duration_s", 0.0),
                input_tokens=usage.get("input_tokens", 0),
                output_tokens=usage.get("output_tokens", 0),
                requests=usage.get("requests", 0),
            )
        )
    return records


def latest_session(cwd: Path) -> Path | None:
    """Return the most recent session-*.jsonl under cwd/.coding-agent/logs, or None."""
    log_dir = cwd / ".coding-agent" / "logs"
    try:
        candidates = list(log_dir.glob("session-*.jsonl"))
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.name)
