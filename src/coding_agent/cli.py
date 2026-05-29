from __future__ import annotations

import argparse
from pathlib import Path

from coding_agent.agent import build_agent
from coding_agent.context import gather_context
from coding_agent.deps import AgentDeps
from coding_agent.pickers import PROVIDERS
from coding_agent.providers import load_env_file
from coding_agent.repl import _build_model, _pick_provider_and_model, run_repl
from coding_agent.session_log import SessionLogger, latest_session, load_session
from pydantic_ai.messages import ModelRequest, UserPromptPart


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
    p.add_argument(
        "--resume",
        nargs="?",
        const="latest",
        default=None,
        help="Resume a past session. Bare --resume or --resume latest = newest; or pass a session-*.jsonl path.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    cwd = Path.cwd().resolve()
    loaded = load_env_file(cwd / ".env")
    deps = AgentDeps(cwd=cwd, auto_approve=args.yolo)  # approved_tools set defaults via field(default_factory=set)

    provider, model_name = _pick_provider_and_model(args)
    model = _build_model(provider, model_name, args.host, args.api_key)

    print(f"\ncoding-agent — provider: {provider}, model: {model_name}")
    print(f"locked to: {cwd}  (cannot escape this directory)")
    if loaded:
        print(f"loaded {loaded} key(s) from .env")
    if args.yolo:
        print("⚠  --yolo: destructive tools will NOT prompt for approval.")
    print("Type /help for commands.\n")

    project_context = gather_context(cwd)
    agent = build_agent(model, project_context=project_context)
    logger = SessionLogger(cwd=cwd, model=f"{provider}:{model_name}")
    print(f"logging session to: {logger.path.relative_to(cwd)}\n")

    if args.resume:
        path = latest_session(cwd) if args.resume == "latest" else Path(args.resume)
        if path and path.exists():
            resumed = load_session(path)
            print(f"resumed {len(resumed)} turns from {path.name}")
            recap = "\n".join(f"User: {rec.user}\nAssistant: {rec.output}" for rec in resumed)
            resume_history = [ModelRequest(parts=[UserPromptPart(content="[Resumed session recap]\n" + recap)])]
        else:
            print(f"--resume: no session found ({args.resume})")
            resume_history = []
    else:
        resume_history = []

    run_repl(agent, deps, logger, args, provider, model_name, model, initial_history=resume_history, project_context=project_context)


if __name__ == "__main__":
    main()
