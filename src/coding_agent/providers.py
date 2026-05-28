"""Model builders for each supported provider, plus a tiny .env loader."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider
from pydantic_ai.providers.openai import OpenAIProvider

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def load_env_file(path: Path) -> int:
    """Load KEY=VAL lines from a .env file into os.environ without overwriting existing keys.

    Returns the count of new keys set. Quotes around values are stripped.
    Comments (lines starting with `#`) and blank lines are ignored.
    """
    if not path.exists() or not path.is_file():
        return 0
    loaded = 0
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
            loaded += 1
    return loaded


def _ollama_base_url(host: str) -> str:
    host = host.rstrip("/")
    return host if host.endswith("/v1") else host + "/v1"


def build_ollama_model(model_name: str, host: str = "http://localhost:11434") -> OpenAIChatModel:
    return OpenAIChatModel(
        model_name=model_name,
        provider=OllamaProvider(base_url=_ollama_base_url(host)),
    )


def build_openrouter_model(model_name: str, api_key: str) -> OpenAIChatModel:
    return OpenAIChatModel(
        model_name=model_name,
        provider=OpenAIProvider(
            base_url=OPENROUTER_BASE_URL,
            api_key=api_key,
        ),
    )
