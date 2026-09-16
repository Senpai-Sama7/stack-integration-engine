"""NEXUS integration over its observed MCP stdio contract."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stack_integration.tools.mcp import McpProtocolError, McpStdioClient

READ_ONLY_TOOLS = {
    "nexus_workspace_overview",
    "nexus_search",
    "nexus_read_span",
    "nexus_index_build",
    "nexus_file_symbols",
    "nexus_find_symbols",
    "nexus_references",
    "nexus_call_graph",
    "nexus_dependency_graph",
    "nexus_impact_analysis",
    "nexus_git_diff",
    "nexus_repo_map",
    "nexus_context_pack",
    "nexus_server_status",
    "nexus_audit_log",
    "nexus_guide",
    "nexus_secret_scan",
    "nexus_audit_manifest",
}


class NexusToolAdapter:
    def __init__(self, server_script: str | Path):
        self.server_script = Path(server_script).expanduser().resolve()
        if not self.server_script.is_file():
            raise FileNotFoundError(self.server_script)

    def client(self, workspace: str | Path) -> McpStdioClient:
        root = Path(workspace).expanduser().resolve()
        return McpStdioClient(
            ["node", str(self.server_script)], cwd=root, env={"NEXUS_WORKSPACE": str(root)}
        )

    async def probe(self, workspace: str | Path) -> dict[str, Any]:
        async with self.client(workspace) as client:
            tools = await client.list_tools()
            names = {item.get("name") for item in tools}
            required = {"nexus_workspace_overview", "nexus_context_pack", "nexus_impact_analysis"}
            return {
                "status": "supported" if required <= names else "degraded",
                "server_script": str(self.server_script),
                "tool_count": len(tools),
                "missing_required": sorted(required - names),
                "read_only_tools": sorted(names & READ_ONLY_TOOLS),
            }

    async def call_read_only(
        self, workspace: str | Path, name: str, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if name not in READ_ONLY_TOOLS:
            raise PermissionError(f"NEXUS tool is not admitted as read-only: {name}")
        async with self.client(workspace) as client:
            available = {tool.get("name") for tool in await client.list_tools()}
            if name not in available:
                raise McpProtocolError(f"NEXUS capability unavailable: {name}")
            return await client.call_tool(name, arguments)

    @staticmethod
    def content_text(result: dict[str, Any]) -> str:
        blocks = result.get("content", [])
        return "\n".join(
            str(block.get("text", ""))
            for block in blocks
            if isinstance(block, dict) and block.get("type") == "text"
        )
