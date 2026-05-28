from __future__ import annotations

from pathlib import Path

import pytest
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart
from pydantic_ai.models.function import AgentInfo, FunctionModel
from pydantic_ai.models.test import TestModel

from coding_agent.agent import build_agent
from coding_agent.deps import AgentDeps


EXPECTED_TOOL_NAMES = {
    "read_file",
    "list_dir",
    "glob_files",
    "grep",
    "write_file",
    "edit_file",
    "run_bash",
}


def test_build_agent_registers_seven_tools():
    agent = build_agent("test")
    m = TestModel()
    with agent.override(model=m):
        agent.run_sync(
            "hello",
            deps=AgentDeps(cwd=Path.cwd(), auto_approve=True),
        )
    tools = m.last_model_request_parameters.function_tools
    names = {t.name for t in tools}
    assert names == EXPECTED_TOOL_NAMES


def test_read_file_via_agent(tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_text("alpha\nbravo\ncharlie")

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[ToolCallPart(tool_name="read_file", args={"path": "sample.txt"})]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "read sample.txt",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "alpha" in blob
    assert "bravo" in blob
    assert "charlie" in blob


def test_write_file_creates_file(tmp_path):
    agent = build_agent("test")
    m = TestModel(call_tools=["write_file"])
    with agent.override(model=m):
        result = agent.run_sync(
            "write something",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    created = list(tmp_path.iterdir())
    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert created or "Wrote" in blob


def test_path_escape_rejected(tmp_path):
    from coding_agent.tools import _safe_path

    with pytest.raises(ValueError):
        _safe_path(tmp_path, "../../etc/passwd")

    safe = _safe_path(tmp_path, "foo/bar")
    assert tmp_path in safe.parents or safe.parent == tmp_path or str(safe).startswith(str(tmp_path))
