"""Local controller configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    state_root: Path
    database_path: Path
    artifacts_path: Path
    nexus_server_script: Path

    @classmethod
    def load(cls, state_root: str | Path | None = None) -> Settings:
        root = (
            Path(
                state_root
                or os.environ.get("STACK_AGENT_STATE")
                or (Path.home() / ".local/state/stack-agent")
            )
            .expanduser()
            .resolve()
        )
        nexus = (
            Path(
                os.environ.get("NEXUS_SERVER_SCRIPT")
                or (Path.home() / "Projects/MCPs/nexus-mcp-server/dist/server.js")
            )
            .expanduser()
            .resolve()
        )
        return cls(root, root / "controller.db", root / "artifacts", nexus)
