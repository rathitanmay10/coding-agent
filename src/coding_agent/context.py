from __future__ import annotations

from pathlib import Path

_SKIP_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "dist",
    "build",
    ".mypy_cache",
}


def _build_tree(cwd: Path) -> str:
    lines: list[str] = []
    try:
        for entry in sorted(cwd.iterdir(), key=lambda e: (e.is_file(), e.name)):
            if entry.is_dir():
                if entry.name in _SKIP_DIRS or entry.name.startswith("."):
                    continue
                lines.append(f"{entry.name}/")
                try:
                    for child in sorted(
                        entry.iterdir(), key=lambda e: (e.is_file(), e.name)
                    ):
                        if child.is_dir():
                            if child.name in _SKIP_DIRS or child.name.startswith("."):
                                continue
                            lines.append(f"  {child.name}/")
                        else:
                            lines.append(f"  {child.name}")
                except OSError:
                    pass
            else:
                lines.append(entry.name)
    except OSError:
        return ""
    if not lines:
        return ""
    truncated = False
    if len(lines) > 60:
        lines = lines[:60]
        truncated = True
    tree = "\n".join(lines)
    if truncated:
        tree += "\n… (truncated)"
    return tree


def gather_context(cwd: Path) -> str:
    """Build a short project-context block: dir tree (depth<=2) + head of a project doc.

    Returned string is appended to the agent system prompt. Empty string if nothing useful.
    """
    tree = _build_tree(cwd)

    doc_content = ""
    doc_label = ""
    for candidate in ("CLAUDE.md", "README.md"):
        doc_path = cwd / candidate
        if doc_path.exists():
            try:
                lines = doc_path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
                doc_content = "\n".join(lines[:100])
                doc_label = candidate
            except OSError:
                pass
            break

    if not tree and not doc_content:
        return ""

    parts: list[str] = []
    if tree:
        parts.append(f"## Project layout\n{tree}")
    if doc_content:
        parts.append(f"## Project doc ({doc_label}, head)\n{doc_content}")
    return "\n\n".join(parts)


def summarize_history(history: list) -> str:
    """Produce a short plaintext summary of prior conversation turns for /compact.

    `history` is a list of pydantic_ai message objects. Extract user prompts and
    assistant text parts best-effort and concatenate into a compact recap.
    """
    lines: list[str] = []
    for msg in history:
        try:
            parts = getattr(msg, "parts", None)
            if not parts:
                continue
            for part in parts:
                try:
                    content = getattr(part, "content", None)
                    if not isinstance(content, str) or not content.strip():
                        continue
                    role = getattr(part, "part_kind", None) or getattr(
                        msg, "kind", "msg"
                    )
                    snippet = content[:200].replace("\n", " ")
                    lines.append(f"- {role}: {snippet}")
                except Exception:
                    pass
        except Exception:
            pass
    if not lines:
        return ""
    return "Summary of earlier conversation:\n" + "\n".join(lines)
