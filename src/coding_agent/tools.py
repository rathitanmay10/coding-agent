from __future__ import annotations

import difflib
import os
import re
import shutil
import subprocess
from pathlib import Path

from pydantic_ai import RunContext

from coding_agent.deps import AgentDeps
from coding_agent.approval import confirm

IGNORE_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
    "dist", "build", ".mypy_cache", ".ruff_cache", ".coding-agent",
}

# Obviously destructive command patterns refused before approval is ever asked.
BASH_DENYLIST = (
    re.compile(r"\brm\b.*\s-[a-zA-Z]*[rf][a-zA-Z]*\s+[/~]"),  # rm -rf /... or ~... (absolute/home target)
    re.compile(r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:"),  # fork bomb
    re.compile(r"\bdd\b.*\bof=/dev/"),  # dd of=/dev/...
    re.compile(r"\bmkfs(\.\w+)?\b"),  # filesystem format
    re.compile(r">\s*/dev/sd[a-z]"),  # write to raw disk
)


def _denied_bash(command: str) -> str | None:
    """Return a reason string if `command` matches a destructive denylist pattern, else None."""
    for pat in BASH_DENYLIST:
        if pat.search(command):
            return f"refused: command matches destructive denylist pattern ({pat.pattern})"
    return None


def _safe_path(cwd: Path, path: str) -> Path:
    """Resolve `path` under cwd. Raise ValueError if it escapes cwd."""
    target = (cwd / path).resolve()
    cwd_resolved = cwd.resolve()
    if not target.is_relative_to(cwd_resolved):
        raise ValueError(f"Path escapes working directory: {path}")
    return target


def register_tools(agent) -> None:
    @agent.tool
    def read_file(
        ctx: RunContext[AgentDeps],
        path: str,
        offset: int = 0,
        limit: int = 2000,
    ) -> str:
        """Read a text file and return numbered lines within [offset, offset+limit)."""
        try:
            target = _safe_path(ctx.deps.cwd, path)
            if not target.exists():
                return f"Error: file not found: {path}"
            if not target.is_file():
                return f"Error: not a file: {path}"
            offset = max(0, offset)
            limit = max(1, min(limit, 50000))
            raw = target.read_bytes()
            if b"\x00" in raw[:8192]:
                return f"Error: {path} appears to be a binary file"
            text = raw.decode("utf-8", errors="replace")
            lines = text.splitlines()
            selected = lines[offset : offset + limit]
            return "\n".join(f"{offset + i + 1}\t{line}" for i, line in enumerate(selected))
        except Exception as e:
            return f"Error: {e}"

    @agent.tool
    def list_dir(ctx: RunContext[AgentDeps], path: str = ".") -> list[str]:
        """List entries in a directory (directories get a trailing slash)."""
        try:
            target = _safe_path(ctx.deps.cwd, path)
            if not target.exists():
                return [f"Error: directory not found: {path}"]
            if not target.is_dir():
                return [f"Error: not a directory: {path}"]
            allowed_dot = {".gitignore", ".env.example"}
            entries: list[str] = []
            for child in target.iterdir():
                name = child.name
                if name.startswith(".") and name not in allowed_dot:
                    continue
                if child.is_dir():
                    entries.append(name + "/")
                else:
                    entries.append(name)
            entries.sort()
            return entries
        except Exception as e:
            return [f"Error: {e}"]

    @agent.tool
    def glob_files(ctx: RunContext[AgentDeps], pattern: str) -> list[str]:
        """Find files matching a glob pattern relative to the working directory."""
        try:
            cwd = ctx.deps.cwd
            results = sorted(
                str(p.relative_to(cwd))
                for p in cwd.glob(pattern)
                if p.is_file() and not any(part in IGNORE_DIRS for part in p.parts)
            )
            if len(results) > 200:
                return results[:200] + ["... (truncated)"]
            return results
        except Exception as e:
            return [f"Error: {e}"]

    @agent.tool
    def grep(
        ctx: RunContext[AgentDeps],
        pattern: str,
        path: str = ".",
        glob: str = "**/*",
    ) -> str:
        """Search file contents for a regex pattern; uses ripgrep if available."""
        try:
            target = _safe_path(ctx.deps.cwd, path)
            if shutil.which("rg"):
                try:
                    proc = subprocess.run(
                        ["rg", "-n", "--no-heading", "-g", glob, pattern, str(target)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                except subprocess.TimeoutExpired:
                    return "Error: grep timed out after 30s (pathological regex?)"
                out = proc.stdout
                if not out.strip():
                    return "(no matches)"
                return out[:4000]
            hits: list[str] = []
            try:
                regex = re.compile(pattern)
            except re.error as e:
                return f"Error: invalid regex: {e}"
            walk_root = target if target.is_dir() else target.parent
            for root, dirs, files in os.walk(walk_root):
                dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
                for fname in files:
                    fpath = Path(root) / fname
                    if not fpath.match(glob):
                        continue
                    if not fpath.is_file():
                        continue
                    try:
                        text = fpath.read_text()
                    except Exception:
                        continue
                    try:
                        relpath = fpath.relative_to(ctx.deps.cwd)
                    except ValueError:
                        relpath = fpath
                    for lineno, line in enumerate(text.splitlines(), start=1):
                        if regex.search(line):
                            hits.append(f"{relpath}:{lineno}:{line}")
                            if len(hits) >= 200:
                                break
                    if len(hits) >= 200:
                        break
                if len(hits) >= 200:
                    break
            if not hits:
                return "(no matches)"
            return "\n".join(hits)
        except Exception as e:
            return f"Error: {e}"

    @agent.tool
    def write_file(ctx: RunContext[AgentDeps], path: str, content: str) -> str:
        """Write content to a file (with user confirmation), creating parent dirs."""
        try:
            target = _safe_path(ctx.deps.cwd, path)
            detail = f"path: {path}\n{len(content.splitlines())} lines, {len(content)} bytes"
            if target.exists():
                detail = "(overwriting existing file)\n" + detail
            if not confirm(ctx.deps, "write_file", detail):
                return "User denied: write_file"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content)
            return f"Wrote {path} ({len(content)} bytes)"
        except Exception as e:
            return f"Error: {e}"

    @agent.tool
    def edit_file(ctx: RunContext[AgentDeps], path: str, old: str, new: str) -> str:
        """Replace a unique `old` string with `new` in a file (with confirmation)."""
        try:
            target = _safe_path(ctx.deps.cwd, path)
            if not target.exists():
                return f"Error: file not found: {path}"
            mtime_before = target.stat().st_mtime_ns
            current = target.read_text()
            if old not in current:
                return f"Error: `old` string not found in {path}"
            n = current.count(old)
            if n > 1:
                return f"Error: `old` matches {n} times in {path}; provide a longer unique string"
            new_content = current.replace(old, new, 1)
            diff = "".join(
                difflib.unified_diff(
                    current.splitlines(keepends=True),
                    new_content.splitlines(keepends=True),
                    fromfile=path,
                    tofile=path,
                    n=2,
                )
            )
            if not confirm(ctx.deps, "edit_file", diff):
                return "User denied: edit_file"
            if target.stat().st_mtime_ns != mtime_before:
                return f"Error: {path} changed externally during approval; re-read and retry"
            target.write_text(new_content)
            return f"Edited {path}"
        except Exception as e:
            return f"Error: {e}"

    @agent.tool
    def multi_edit(ctx: RunContext[AgentDeps], path: str, edits: list[dict]) -> str:
        """Apply multiple old->new replacements to a file atomically (each 'old' must be unique). Confirms once with a unified diff before writing."""
        try:
            target = _safe_path(ctx.deps.cwd, path)
            if not target.exists():
                return f"Error: file not found: {path}"
            mtime_before = target.stat().st_mtime_ns
            original = target.read_text()
            working = original
            for i, edit in enumerate(edits):
                old = edit.get("old", "")
                new = edit.get("new", "")
                count = working.count(old)
                if count == 0:
                    return f"Error: edit {i}: `old` string not found in current text"
                if count > 1:
                    return f"Error: edit {i}: `old` matches {count} times; provide a longer unique string"
                working = working.replace(old, new, 1)
            diff = "".join(
                difflib.unified_diff(
                    original.splitlines(keepends=True),
                    working.splitlines(keepends=True),
                    fromfile=path,
                    tofile=path,
                    n=2,
                )
            )
            if not confirm(ctx.deps, "multi_edit", diff):
                return "User denied: multi_edit"
            if target.stat().st_mtime_ns != mtime_before:
                return f"Error: {path} changed externally during approval; re-read and retry"
            target.write_text(working)
            return f"Applied {len(edits)} edits to {path}"
        except Exception as e:
            return f"Error: {e}"

    @agent.tool
    def delete_file(ctx: RunContext[AgentDeps], path: str) -> str:
        """Delete a file (with user confirmation)."""
        try:
            target = _safe_path(ctx.deps.cwd, path)
            if not target.exists():
                return f"Error: file not found: {path}"
            if not target.is_file():
                return f"Error: not a file: {path}"
            if not confirm(ctx.deps, "delete_file", f"path: {path}"):
                return "User denied: delete_file"
            target.unlink()
            return f"Deleted {path}"
        except Exception as e:
            return f"Error: {e}"

    @agent.tool
    def move_file(ctx: RunContext[AgentDeps], src: str, dst: str) -> str:
        """Move/rename a file within the working directory (with user confirmation)."""
        try:
            src_target = _safe_path(ctx.deps.cwd, src)
            dst_target = _safe_path(ctx.deps.cwd, dst)
            if not src_target.exists():
                return f"Error: source not found: {src}"
            if not confirm(ctx.deps, "move_file", f"{src} -> {dst}"):
                return "User denied: move_file"
            dst_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src_target), str(dst_target))
            return f"Moved {src} -> {dst}"
        except Exception as e:
            return f"Error: {e}"

    @agent.tool
    def run_bash(ctx: RunContext[AgentDeps], command: str, timeout: int = 60) -> str:
        """Run a shell command in the working directory (with confirmation)."""
        try:
            denied = _denied_bash(command)
            if denied:
                return f"Error: {denied}"
            detail = f"$ {command}\n(cwd: {ctx.deps.cwd})\ntimeout: {timeout}s"
            if not confirm(ctx.deps, "run_bash", detail):
                return "User denied: run_bash"
            try:
                proc = subprocess.run(
                    command,
                    shell=True,
                    cwd=ctx.deps.cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
            except subprocess.TimeoutExpired:
                return f"Error: command timed out after {timeout}s"
            stdout = proc.stdout or ""
            stderr = proc.stderr or ""
            return f"[exit {proc.returncode}]\nstdout:\n{stdout[:4000]}\nstderr:\n{stderr[:2000]}"
        except Exception as e:
            return f"Error: {e}"
