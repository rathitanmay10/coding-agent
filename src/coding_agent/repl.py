from __future__ import annotations

import argparse
import asyncio
import sys
import time
from collections.abc import AsyncIterable

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

from pydantic_ai.messages import ModelRequest, UserPromptPart

from coding_agent.agent import build_agent
from coding_agent.context import summarize_history
from coding_agent.pickers import (
    pick_ollama_model,
    pick_openrouter_model,
    pick_provider,
    resolve_openrouter_key,
)
from coding_agent.providers import (
    build_ollama_model,
    build_openrouter_model,
    with_retry,
)
from coding_agent.session_log import SessionLogger, TurnRecord


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


def run_repl(
    agent,
    deps,
    logger: SessionLogger,
    args: argparse.Namespace,
    provider: str,
    model_name: str,
    model,
    *,
    initial_history: list | None = None,
    project_context: str | None = None,
) -> None:
    history: list = list(initial_history) if initial_history else []

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
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
                provider, model_name = _pick_provider_and_model(
                    args, use_cli_overrides=False
                )
                model = _build_model(provider, model_name, args.host, args.api_key)
                agent = build_agent(model, project_context=project_context)
                history = []
                print(f"(switched to {provider}:{model_name}; history cleared)")
                continue
            if user_input == "/help":
                print(
                    "Commands:\n"
                    "  /help     show this help\n"
                    "  /exit     quit (also /quit)\n"
                    "  /clear    clear conversation history\n"
                    "  /compact  summarize & shrink history to save context\n"
                    "  /model    switch provider/model (clears history)\n"
                    "  /stats    show token usage + log path"
                )
                continue
            if user_input == "/compact":
                old_len = len(history)
                if history:

                    async def _compact():
                        result = await agent.run(
                            "Summarize our conversation so far into a concise recap that "
                            "preserves all decisions, file paths, code changes, and open "
                            "tasks. Write it as notes for continuing the work.",
                            message_history=history,
                            deps=deps,
                        )
                        return str(result.output)

                    try:
                        summary = with_retry(
                            lambda: loop.run_until_complete(_compact())
                        )
                    except Exception as e:
                        print(
                            f"(compact summarization failed: {e}; using fallback)",
                            file=sys.stderr,
                        )
                        summary = summarize_history(history)
                else:
                    summary = ""
                if summary:
                    history = [
                        ModelRequest(
                            parts=[
                                UserPromptPart(
                                    content="[Compacted context]\n" + summary
                                )
                            ]
                        )
                    ]
                else:
                    history = []
                print(f"(history compacted: {old_len} turns -> summary)")
                continue

            turn_calls: list[dict] = []
            handler = make_event_handler(turn_calls)
            rec = TurnRecord(user=user_input)
            t0 = time.monotonic()

            async def _run_turn():
                async with agent.run_stream(
                    user_input,
                    message_history=history,
                    deps=deps,
                    event_stream_handler=handler,
                ) as response:
                    print()
                    async for chunk in response.stream_text(delta=True):
                        print(chunk, end="", flush=True)
                    print()
                    output = str(await response.get_output())
                    usage_tuple = _extract_usage(response)
                    new_msgs = response.new_messages()
                return output, usage_tuple, new_msgs

            try:
                output, usage_tuple, new_msgs = with_retry(
                    lambda: loop.run_until_complete(_run_turn())
                )
            except KeyboardInterrupt:
                # The interrupted turn left a pending task (agent.run_stream's async
                # context) on the reused loop; cancel + drain it so the streaming HTTP
                # connection is closed instead of leaked.
                try:
                    pending = asyncio.all_tasks(loop)
                    for task in pending:
                        task.cancel()
                    if pending:
                        loop.run_until_complete(
                            asyncio.gather(*pending, return_exceptions=True)
                        )
                    loop.run_until_complete(loop.shutdown_asyncgens())
                except Exception:
                    pass
                rec.error = "cancelled"
                rec.tool_calls = turn_calls
                rec.duration_s = time.monotonic() - t0
                logger.log_turn(rec)
                print("\n(turn cancelled)\n", file=sys.stderr)
                continue
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
            rec.output = output
            rec.input_tokens, rec.output_tokens, rec.requests = usage_tuple
            logger.log_turn(rec)
            history.extend(new_msgs)

            print(logger.metrics_line(rec), file=sys.stderr)
            print()
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
