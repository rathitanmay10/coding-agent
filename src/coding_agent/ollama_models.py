import time

import httpx

_CACHE: dict = {"ts": 0.0, "host": "", "models": []}


def list_models(
    host: str = "http://localhost:11434",
    max_age: float = 5.0,
) -> list[str]:
    """Return locally-installed Ollama model names (cached for `max_age` seconds)."""
    now = time.monotonic()
    if _CACHE["host"] == host and (now - _CACHE["ts"]) < max_age:
        return list(_CACHE["models"])
    try:
        response = httpx.get(f"{host}/api/tags", timeout=5.0)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        raise RuntimeError(
            f"Could not reach Ollama at {host}. Is `ollama serve` running?"
        ) from e
    models = sorted(m["name"] for m in data.get("models", []))
    _CACHE.update({"ts": now, "host": host, "models": models})
    return models
