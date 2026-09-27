"""Compatibility wrapper around the verified NEXUS MCP stdio adapter."""

import os
from pathlib import Path
from typing import Any

from stack_integration.tools import NexusToolAdapter


class NexusAdapter:
    def __init__(self, workspace: str = ".", server_script: str | None = None):
        candidate = server_script or os.environ.get(
            "NEXUS_SERVER_SCRIPT",
            str(Path.home() / "Projects/MCPs/nexus-mcp-server/dist/server.js"),
        )
        self.workspace = str(Path(workspace).resolve())
        self.adapter = NexusToolAdapter(candidate)

    async def workspace_overview(self, workspace: str | None = None) -> dict[str, Any]:
        return await self.adapter.call_read_only(
            workspace or self.workspace, "nexus_workspace_overview", {}
        )

    async def impact_analysis(self, target: str, mode: str = "symbol") -> dict[str, Any]:
        return await self.adapter.call_read_only(
            self.workspace, "nexus_impact_analysis", {"target": target, "mode": mode}
        )

    async def context_pack(
        self, focus_files: list[str] | None = None, token_budget: int = 8000
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {"tokenBudget": token_budget}
        if focus_files:
            arguments["focusFiles"] = focus_files
        return await self.adapter.call_read_only(self.workspace, "nexus_context_pack", arguments)

    async def test_run(self, framework: str | None = None) -> dict[str, Any]:
        raise PermissionError("test execution must use the independent verification runner")

    async def close(self) -> None:
        return None
