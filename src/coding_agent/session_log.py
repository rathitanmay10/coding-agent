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
        self._write({
            "type": "session_start",
            "ts": time.time(),
            "model": model,
            "cwd": str(cwd),
        })

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
        self._write({
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
        })

    def metrics_line(self, last: TurnRecord) -> str:
        return (
            f"[turn {self.turn_count}] "
            f"in={last.input_tokens} out={last.output_tokens} "
            f"req={last.requests} t={last.duration_s:.2f}s | "
            f"session total: in={self.total_input} out={self.total_output} "
            f"req={self.total_requests}"
        )
