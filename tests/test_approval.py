from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.approval import confirm
from coding_agent.deps import AgentDeps


def _deps(**kwargs) -> AgentDeps:
    return AgentDeps(cwd=Path("."), **kwargs)


def test_auto_approve_no_input(monkeypatch):
    def boom(*_):
        raise AssertionError("input() should not be called")

    monkeypatch.setattr("builtins.input", boom)
    deps = _deps(auto_approve=True)
    assert confirm(deps, "write_file", "some detail") is True


def test_already_approved_tool_no_input(monkeypatch):
    def boom(*_):
        raise AssertionError("input() should not be called")

    monkeypatch.setattr("builtins.input", boom)
    deps = _deps(approved_tools={"run_bash"})
    assert confirm(deps, "run_bash", "detail") is True


def test_input_y_returns_true(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "y")
    deps = _deps()
    assert confirm(deps, "run_bash", "") is True
    assert "run_bash" not in deps.approved_tools


def test_input_yes_returns_true(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "yes")
    deps = _deps()
    assert confirm(deps, "write_file", "") is True


def test_input_n_returns_false(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "n")
    deps = _deps()
    assert confirm(deps, "run_bash", "") is False


def test_input_empty_returns_false(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "")
    deps = _deps()
    assert confirm(deps, "run_bash", "") is False


def test_input_garbage_returns_false(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "garbage")
    deps = _deps()
    assert confirm(deps, "run_bash", "") is False


def test_input_a_adds_to_approved_and_returns_true(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda *_: "a")
    deps = _deps()
    result = confirm(deps, "write_file", "")
    assert result is True
    assert "write_file" in deps.approved_tools


def test_input_a_then_second_call_no_prompt(monkeypatch):
    call_count = 0

    def counted_input(*_):
        nonlocal call_count
        call_count += 1
        return "a"

    monkeypatch.setattr("builtins.input", counted_input)
    deps = _deps()
    confirm(deps, "write_file", "")
    assert call_count == 1

    def boom(*_):
        raise AssertionError("input() should not be called on second confirm")

    monkeypatch.setattr("builtins.input", boom)
    assert confirm(deps, "write_file", "") is True


def test_eoferror_returns_false(monkeypatch):
    def raise_eof(*_):
        raise EOFError

    monkeypatch.setattr("builtins.input", raise_eof)
    deps = _deps()
    assert confirm(deps, "run_bash", "") is False
