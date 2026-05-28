from __future__ import annotations

import argparse
import getpass
import os
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
from coding_agent.providers import (
    build_ollama_model,
    build_openrouter_model,
    load_env_file,
)
from coding_agent.session_log import SessionLogger, TurnRecord

PROVIDERS = ("ollama", "openrouter")
OPENROUTER_SUGGESTIONS = (
    "z-ai/glm-4.5-air:free",
    "openrouter/free"
)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        prog="coding-agent",
        description="Local CLI coding agent (Ollama / OpenRouter via Pydantic AI)",
    )
    p.add_argument(
        "--provider",
        choices=PROVIDERS,
        help="Skip provider picker.",
    )
    p.add_argument(
        "--model",
        help="Model name. Skips model picker.",
    )
    p.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama host URL (ignored for openrouter).",
    )
    p.add_argument(
        "--api-key",
        dest="api_key",
        default=None,
        help="OpenRouter API key. Falls back to OPENROUTER_API_KEY env / .env / prompt.",
    )
    p.add_argument(
        "--yolo",
        action="store_true",
        help="Auto-approve all destructive tool calls.",
    )
    return p.parse_args()


def _safe_input(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def pick_provider() -> str:
    print("Providers:")
    for i, name in enumerate(PROVIDERS, 1):
        suffix = "(local)" if name == "ollama" else "(cloud)"
        print(f"  {i}. {name} {suffix}")
    while True:
        raw = _safe_input(f"Pick [1-{len(PROVIDERS)}]: ")
        if raw.isdigit() and 1 <= int(raw) <= len(PROVIDERS):
            return PROVIDERS[int(raw) - 1]
        if raw in PROVIDERS:
            return raw
        print("Invalid choice.")


def pick_ollama_model(host: str) -> str:
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
        raw = _safe_input(f"Pick [1-{len(models)}]: ")
        if raw.isdigit() and 1 <= int(raw) <= len(models):
            return models[int(raw) - 1]
        print("Invalid choice.")


def pick_openrouter_model() -> str:
    print("Common OpenRouter models:")
    for i, name in enumerate(OPENROUTER_SUGGESTIONS, 1):
        print(f"  {i}. {name}")
    print("  Or type any other slug from https://openrouter.ai/models")
    while True:
        raw = _safe_input("Model: ")
        if not raw:
            continue
        if raw.isdigit() and 1 <= int(raw) <= len(OPENROUTER_SUGGESTIONS):
            return OPENROUTER_SUGGESTIONS[int(raw) - 1]
        if "/" in raw:
            return raw
        print("Model slugs look like `vendor/model-name`. Try again.")


def resolve_openrouter_key(cli_key: str | None) -> str:
    if cli_key:
        return cli_key
    env_key = os.environ.get("OPENROUTER_API_KEY")
    if env_key:
        return env_key
    key = getpass.getpass("OpenRouter API key (input hidden): ").strip()
    if not key:
        print("No API key provided; cannot use OpenRouter.", file=sys.stderr)
        sys.exit(1)
    return key


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


def _build_model(
    provider: str,
    model_name: str,
    host: str,
    api_key: str | None,
):
    if provider == "ollama":
        return build_ollama_model(model_name, host=host)
    if provider == "openrouter":
        key = resolve_openrouter_key(api_key)
        return build_openrouter_model(model_name, api_key=key)
    raise ValueError(f"Unknown provider: {provider}")


def _pick_provider_and_model(
    args: argparse.Namespace,
    *,
    use_cli_overrides: bool = True,
) -> tuple[str, str]:
    provider = (args.provider if use_cli_overrides else None) or pick_provider()
    cli_model = args.model if use_cli_overrides else None
    if cli_model:
        return provider, cli_model
    if provider == "ollama":
        return provider, pick_ollama_model(args.host)
    return provider, pick_openrouter_model()


def main() -> None:
    args = parse_args()
    cwd = Path.cwd().resolve()
    loaded = load_env_file(cwd / ".env")
    deps = AgentDeps(cwd=cwd, auto_approve=args.yolo)

    provider, model_name = _pick_provider_and_model(args)
    model = _build_model(provider, model_name, args.host, args.api_key)

    print(f"\ncoding-agent — provider: {provider}, model: {model_name}")
    print(f"locked to: {cwd}  (cannot escape this directory)")
    if loaded:
        print(f"loaded {loaded} key(s) from .env")
    if args.yolo:
        print("⚠  --yolo: destructive tools will NOT prompt for approval.")
    print("Type /exit, /clear, /model, /stats.\n")

    agent = build_agent(model)
    history: list = []
    logger = SessionLogger(cwd=cwd, model=f"{provider}:{model_name}")
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
            provider, model_name = _pick_provider_and_model(args, use_cli_overrides=False)
            model = _build_model(provider, model_name, args.host, args.api_key)
            agent = build_agent(model)
            history = []
            print(f"(switched to {provider}:{model_name}; history cleared)")
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
