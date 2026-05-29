from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AgentDeps:
    cwd: Path
    auto_approve: bool = False
    approved_tools: set[str] = field(default_factory=set)
    bash_allowlist: list[str] = field(default_factory=list)
    max_stdout: int = 4000
    max_stderr: int = 2000
