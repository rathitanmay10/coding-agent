"""Single y/N confirmation gate for destructive tool calls."""

import sys


def confirm(deps, action: str, detail: str) -> bool:
    """Prompt user to approve a destructive action. Returns True on approval.

    If deps.auto_approve is True, returns True without prompting.
    If action is in deps.approved_tools, returns True without prompting.
    Prompting with 'a'/'always' adds action to deps.approved_tools for the session.
    """
    if deps.auto_approve:
        return True

    if action in deps.approved_tools:
        return True

    border = "─" * 3
    print(f"\n{border} {action} {border}", file=sys.stderr)
    if detail:
        print(detail, file=sys.stderr)
    try:
        answer = input("Approve? [y/N/a] ").strip().lower()
    except EOFError:
        return False
    if answer in ("a", "always"):
        deps.approved_tools.add(action)
        return True
    return answer in ("y", "yes")
