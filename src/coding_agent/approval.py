"""Single y/N confirmation gate for destructive tool calls."""

import sys


def confirm(action: str, detail: str, auto_approve: bool = False) -> bool:
    """Prompt user to approve a destructive action. Returns True on approval.

    If auto_approve is True, returns True without prompting.
    """
    if auto_approve:
        return True

    border = "─" * 3
    print(f"\n{border} {action} {border}", file=sys.stderr)
    if detail:
        print(detail, file=sys.stderr)
    try:
        answer = input("Approve? [y/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")
