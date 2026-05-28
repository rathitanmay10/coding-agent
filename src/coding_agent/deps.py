from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentDeps:
    cwd: Path
    auto_approve: bool = False
