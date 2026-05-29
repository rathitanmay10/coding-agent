from __future__ import annotations

from pathlib import Path

import pytest

from coding_agent.context import gather_context


def test_tree_includes_pkg_and_doc_excludes_junk(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text("# module")
    (tmp_path / "README.md").write_text("project readme\nsecond line")
    (tmp_path / ".venv").mkdir()
    (tmp_path / ".venv" / "x.py").write_text("")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "y.js").write_text("")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "z.pyc").write_bytes(b"")

    result = gather_context(tmp_path)

    assert result != ""
    assert "pkg" in result
    assert "project readme" in result
    assert ".venv" not in result
    assert "node_modules" not in result
    assert "__pycache__" not in result


def test_claude_md_preferred_over_readme(tmp_path):
    (tmp_path / "CLAUDE.md").write_text("claude content here")
    (tmp_path / "README.md").write_text("readme content here")

    result = gather_context(tmp_path)

    assert "claude content here" in result
    assert "CLAUDE.md" in result
    assert "readme content here" not in result


def test_empty_dir_returns_empty_string(tmp_path):
    result = gather_context(tmp_path)
    assert result == ""


def test_long_doc_truncated_at_100_lines(tmp_path):
    lines = [f"line {i}" for i in range(200)]
    (tmp_path / "README.md").write_text("\n".join(lines))

    result = gather_context(tmp_path)

    assert "line 0" in result
    assert "line 99" in result
    assert "line 150" not in result
