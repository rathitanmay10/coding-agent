from __future__ import annotations

import os
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
    "multi_edit",
    "delete_file",
    "move_file",
}


def test_build_agent_registers_all_tools():
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
    assert (
        tmp_path in safe.parents
        or safe.parent == tmp_path
        or str(safe).startswith(str(tmp_path))
    )


# ---------------------------------------------------------------------------
# glob_files: gitignore-style dirs are skipped
# ---------------------------------------------------------------------------


def test_glob_files_skips_ignored_dirs(tmp_path):
    real = tmp_path / "pkg" / "mod.py"
    real.parent.mkdir(parents=True)
    real.write_text("x = 1")

    venv_file = tmp_path / ".venv" / "lib" / "junk.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text("junk")

    cache_file = tmp_path / "__pycache__" / "x.py"
    cache_file.parent.mkdir(parents=True)
    cache_file.write_text("cache")

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="glob_files", args={"pattern": "**/*.py"})
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "glob py files",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "pkg" + os.sep + "mod.py" in blob or "pkg/mod.py" in blob
    assert ".venv" not in blob
    assert "__pycache__" not in blob


# ---------------------------------------------------------------------------
# grep python fallback: ignored dirs skipped when rg absent
# ---------------------------------------------------------------------------


def test_grep_fallback_skips_ignored_dirs(tmp_path, monkeypatch):
    import coding_agent.tools as _tools_mod

    monkeypatch.setattr(_tools_mod.shutil, "which", lambda name: None)

    normal = tmp_path / "src" / "app.py"
    normal.parent.mkdir(parents=True)
    normal.write_text("SECRET = 'hello'\n")

    venv_file = tmp_path / ".venv" / "lib" / "pkg.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text("SECRET = 'hello'\n")

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[ToolCallPart(tool_name="grep", args={"pattern": "SECRET"})]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "grep SECRET",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "src" in blob
    assert ".venv" not in blob


# ---------------------------------------------------------------------------
# multi_edit
# ---------------------------------------------------------------------------


def test_multi_edit_applies_two_edits(tmp_path):
    f = tmp_path / "code.py"
    f.write_text("foo = 1\nbar = 2\nbaz = 3\n")

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="multi_edit",
                        args={
                            "path": "code.py",
                            "edits": [
                                {"old": "foo = 1", "new": "foo = 100"},
                                {"old": "bar = 2", "new": "bar = 200"},
                            ],
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "multi edit code.py",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "Applied 2 edits to code.py" in blob
    content = f.read_text()
    assert "foo = 100" in content
    assert "bar = 200" in content
    assert "baz = 3" in content


def test_multi_edit_atomic_on_missing_old(tmp_path):
    f = tmp_path / "code.py"
    original = "alpha\nbeta\ngamma\n"
    f.write_text(original)

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="multi_edit",
                        args={
                            "path": "code.py",
                            "edits": [
                                {"old": "alpha", "new": "ALPHA"},
                                {"old": "DOES_NOT_EXIST", "new": "x"},
                            ],
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "multi edit code.py",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "Error" in blob
    assert f.read_text() == original


def test_multi_edit_atomic_on_duplicate_old(tmp_path):
    f = tmp_path / "code.py"
    original = "x = 1\nx = 1\n"
    f.write_text(original)

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="multi_edit",
                        args={
                            "path": "code.py",
                            "edits": [
                                {"old": "x = 1", "new": "x = 99"},
                            ],
                        },
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "multi edit code.py",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "Error" in blob
    assert f.read_text() == original


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------


def test_delete_file_removes_file(tmp_path):
    f = tmp_path / "to_delete.txt"
    f.write_text("bye")

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="delete_file", args={"path": "to_delete.txt"}
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "delete to_delete.txt",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "Deleted to_delete.txt" in blob
    assert not f.exists()


def test_delete_file_missing_returns_error(tmp_path):
    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[
                    ToolCallPart(tool_name="delete_file", args={"path": "ghost.txt"})
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "delete ghost.txt",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "Error" in blob


# ---------------------------------------------------------------------------
# move_file
# ---------------------------------------------------------------------------


def test_move_file_relocates_content(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("hello move")

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="move_file",
                        args={"src": "src.txt", "dst": "dst.txt"},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "move src.txt dst.txt",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "Moved src.txt -> dst.txt" in blob
    assert not src.exists()
    dst = tmp_path / "dst.txt"
    assert dst.exists()
    assert dst.read_text() == "hello move"


def test_move_file_path_escape_rejected(tmp_path):
    src = tmp_path / "src.txt"
    src.write_text("data")

    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[
                    ToolCallPart(
                        tool_name="move_file",
                        args={"src": "src.txt", "dst": "../outside.txt"},
                    )
                ]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "move src.txt ../outside.txt",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "Error" in blob
    assert src.exists()


# ---------------------------------------------------------------------------
# _safe_path symlink escape
# ---------------------------------------------------------------------------


def test_safe_path_symlink_escape(tmp_path):
    from coding_agent.tools import _safe_path

    outside = tmp_path.parent
    link = tmp_path / "thelink"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unsupported on this platform")

    with pytest.raises(ValueError):
        _safe_path(tmp_path, "thelink/secret")


# ---------------------------------------------------------------------------
# run_bash denylist — destructive commands refused before approval/execution
# ---------------------------------------------------------------------------


def test_run_bash_denylist(tmp_path):
    called = {"done": False}

    async def fake_model(messages, info: AgentInfo) -> ModelResponse:
        if not called["done"]:
            called["done"] = True
            return ModelResponse(
                parts=[ToolCallPart(tool_name="run_bash", args={"command": "rm -rf /"})]
            )
        return ModelResponse(parts=[TextPart(content="done")])

    agent = build_agent("test")
    # auto_approve=True proves the denylist refuses BEFORE the approval gate.
    with agent.override(model=FunctionModel(fake_model)):
        result = agent.run_sync(
            "wipe disk",
            deps=AgentDeps(cwd=tmp_path, auto_approve=True),
        )

    blob = "\n".join(str(msg) for msg in result.all_messages())
    assert "denylist" in blob


def test_run_bash_denylist_unit():
    from coding_agent.tools import _denied_bash

    assert _denied_bash("rm -rf /") is not None
    assert _denied_bash("rm -rf ~") is not None
    assert _denied_bash(":(){ :|:& };:") is not None
    assert _denied_bash("dd if=/dev/zero of=/dev/sda") is not None
    assert _denied_bash("mkfs.ext4 /dev/sdb1") is not None
    # benign commands pass through
    assert _denied_bash("ls -la") is None
    assert _denied_bash("rm -rf build/") is None
    assert _denied_bash("pytest -q") is None
