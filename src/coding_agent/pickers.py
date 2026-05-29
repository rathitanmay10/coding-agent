from __future__ import annotations

import getpass
import os
import sys

from coding_agent.ollama_models import list_models

PROVIDERS = ("ollama", "openrouter")
OPENROUTER_SUGGESTIONS = (
    "z-ai/glm-4.5-air:free",
    "openrouter/free"
)


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
