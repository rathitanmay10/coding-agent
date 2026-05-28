from __future__ import annotations

from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.ollama import OllamaProvider

from coding_agent.deps import AgentDeps
from coding_agent.tools import register_tools

SYSTEM_PROMPT = """You are a local coding assistant running inside the user's project directory.

You have these tools — call them as needed:
- read_file(path, offset=0, limit=2000): read a file; lines are prefixed with line number + tab
- list_dir(path="."): list directory entries
- glob_files(pattern): find files matching a glob (e.g. "**/*.py")
- grep(pattern, path=".", glob="**/*"): regex search through files
- write_file(path, content): create or overwrite a file
- edit_file(path, old, new): replace ONE unique occurrence of `old` with `new` in a file
- run_bash(command, timeout=60): run a shell command in the project root

Rules:
1. Before editing a file, ALWAYS read it first so you know the exact text.
2. For `edit_file`, the `old` argument must be a UNIQUE substring of the file. Include enough context (a full line plus a neighbor) to make it unique.
3. Prefer `edit_file` over `write_file` for small changes. Use `write_file` for new files or full rewrites.
4. write_file, edit_file, and run_bash will prompt the user for approval — they may decline. If denied, ask what they want instead.
5. Paths are relative to the project root. You cannot escape it.
6. Be concise. Explain what you did after tool calls succeed.
"""


def _ollama_base_url(host: str) -> str:
    host = host.rstrip("/")
    if host.endswith("/v1"):
        return host
    return host + "/v1"


def build_agent(
    model_name: str,
    host: str = "http://localhost:11434",
) -> Agent[AgentDeps, str]:
    """Build an Agent wired for the given Ollama model name and host.

    `model_name` is the bare Ollama model identifier (e.g. 'qwen2.5-coder:7b').
    `host` is the Ollama base URL (the '/v1' suffix is appended automatically).
    """
    model = OpenAIChatModel(
        model_name=model_name,
        provider=OllamaProvider(base_url=_ollama_base_url(host)),
    )
    agent = Agent(
        model,
        deps_type=AgentDeps,
        instructions=SYSTEM_PROMPT,
    )
    register_tools(agent)
    return agent
