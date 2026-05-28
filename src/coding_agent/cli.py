from __future__ import annotations

import argparse
import sys
import time
from collections.abc import AsyncIterable
from pathlib import Path

from pydantic_ai import RunContext

try:
    from pydantic_ai.messages import (
        FunctionToolCallEvent,
        FunctionToolResultEvent,
    )
except ImportError:  # pragma: no cover - fallback for alt layouts
    from pydantic_ai import (  # type: ignore[no-redef]
        FunctionToolCallEvent,
        FunctionToolResultEvent,
    )

from coding_agent.agent import build_agent
from coding_agent.deps import AgentDeps
from coding_agent.ollama_models import list_models
from coding_agent.session_log import SessionLogger, TurnRecord


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="coding-agent",
        description="Local CLI coding agent (Ollama + Pydantic AI)",
    )
    p.add_argument(
        "--model",
        help="Ollama model name, e.g. qwen2.5-coder:7b. Skips picker.",
    )
    p.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama host URL",
    )
    p.add_argument(
        "--yolo",
        action="store_true",
        help="Auto-approve all destructive tool calls",
    )
    return p.parse_args()


def pick_model(host: str) -> str:
    """Show numbered list, return selected model name (without ollama: prefix)."""
    try:
        models = list_models(host)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    if not models:
        print(
            f"No models found at {host}. Run `ollama pull <model>` first.",
            file=sys.stderr,
        )
        sys.exit(1)
    print("Available Ollama models:")
    for i, name in enumerate(models, 1):
        print(f"  {i}. {name}")
    while True:
        try:
            raw = input(f"Pick [1-{len(models)}]: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            sys.exit(0)
        if raw.isdigit() and 1 <= int(raw) <= len(models):
            return models[int(raw) - 1]
        print("Invalid choice.")


def make_event_handler(turn_calls: list[dict]):
    """Return an async event-stream handler that prints tool calls and appends them to turn_calls."""

    async def handler(ctx: RunContext, events: AsyncIterable) -> None:
        async for event in events:
            if isinstance(event, FunctionToolCallEvent):
                args = event.part.args if hasattr(event.part, "args") else ""
                args_str = str(args)
                turn_calls.append({"name": event.part.tool_name, "args": args})
                shown = args_str if len(args_str) <= 120 else args_str[:120] + "..."
                print(f"  → {event.part.tool_name}({shown})", file=sys.stderr)
            elif isinstance(event, FunctionToolResultEvent):
                content = getattr(event.result, "content", "")
                content_str = str(content)
                if len(content_str) > 200:
                    content_str = content_str[:200] + "..."
                print(f"    ↳ {content_str}", file=sys.stderr)

    return handler


def _print_session_total(logger: SessionLogger) -> None:
    print(
        f"session total: in={logger.total_input} out={logger.total_output} "
        f"req={logger.total_requests} turns={logger.turn_count}",
        file=sys.stderr,
    )


def _extract_usage(result) -> tuple[int, int, int]:
    """Return (input_tokens, output_tokens, requests) from a run result."""
    usage = result.usage
    if usage is None:
        return (0, 0, 0)
    return (
        getattr(usage, "input_tokens", 0) or 0,
        getattr(usage, "output_tokens", 0) or 0,
        getattr(usage, "requests", 0) or 0,
    )


def main() -> None:
    args = parse_args()
    cwd = Path.cwd().resolve()
    deps = AgentDeps(cwd=cwd, auto_approve=args.yolo)

    model_name = args.model or pick_model(args.host)

    print(f"\ncoding-agent — model: {model_name}")
    print(f"locked to: {cwd}  (cannot escape this directory)")
    if args.yolo:
        print("⚠  --yolo: destructive tools will NOT prompt for approval.")
    print("Type /exit, /clear, /model, /stats.\n")

    agent = build_agent(model_name, host=args.host)
    history: list = []
    logger = SessionLogger(cwd=cwd, model=model_name)
    print(f"logging session to: {logger.path.relative_to(cwd)}\n")

    while True:
        try:
            user_input = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            _print_session_total(logger)
            return

        if not user_input:
            continue
        if user_input in ("/exit", "/quit"):
            _print_session_total(logger)
            return
        if user_input == "/clear":
            history = []
            print("(history cleared)")
            continue
        if user_input == "/stats":
            print(
                f"turns={logger.turn_count} "
                f"in={logger.total_input} out={logger.total_output} "
                f"req={logger.total_requests} "
                f"log={logger.path}"
            )
            continue
        if user_input == "/model":
            model_name = pick_model(args.host)
            agent = build_agent(model_name, host=args.host)
            history = []
            print(f"(switched to {model_name}; history cleared)")
            continue

        turn_calls: list[dict] = []
        handler = make_event_handler(turn_calls)
        rec = TurnRecord(user=user_input)
        t0 = time.monotonic()
        try:
            result = agent.run_sync(
                user_input,
                message_history=history,
                deps=deps,
                event_stream_handler=handler,
            )
        except Exception as e:
            rec.error = str(e)
            rec.tool_calls = turn_calls
            rec.duration_s = time.monotonic() - t0
            logger.log_turn(rec)
            print(f"\nError: {e}\n", file=sys.stderr)
            print(logger.metrics_line(rec), file=sys.stderr)
            continue

        rec.duration_s = time.monotonic() - t0
        rec.tool_calls = turn_calls
        rec.output = str(result.output)
        rec.input_tokens, rec.output_tokens, rec.requests = _extract_usage(result)
        logger.log_turn(rec)
        history.extend(result.new_messages())

        print(f"\n{result.output}\n")
        print(logger.metrics_line(rec), file=sys.stderr)
        print()


if __name__ == "__main__":
    main()
