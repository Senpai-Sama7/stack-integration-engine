"""Adapter for nexus-mcp-server."""

import logging
import httpx
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class NexusAdapter:
    """Adapter for communicating with NEXUS service."""

    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self.logger = logger

    async def workspace_overview(self, workspace: str) -> Dict[str, Any]:
        """Get workspace overview.

        Args:
            workspace: Workspace path

        Returns:
            Overview data
        """
        self.logger.info(f"Getting workspace overview for {workspace}")
        try:
            response = await self.client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "nexus_workspace_overview",
                        "arguments": {}
                    }
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Workspace overview failed: {e}")
            raise

    async def impact_analysis(self, target: str, mode: str = "symbol") -> Dict[str, Any]:
        """Analyze impact of changing a symbol.

        Args:
            target: Symbol name or file path
            mode: "symbol" or "file"

        Returns:
            Impact analysis
        """
        self.logger.info(f"Running impact analysis on {target}")
        try:
            response = await self.client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "nexus_impact_analysis",
                        "arguments": {"target": target, "mode": mode}
                    }
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Impact analysis failed: {e}")
            raise

    async def context_pack(
        self,
        focus_files: Optional[List[str]] = None,
        token_budget: int = 8000,
    ) -> Dict[str, Any]:
        """Get token-budgeted context pack.

        Args:
            focus_files: Files to prioritize
            token_budget: Maximum tokens

        Returns:
            Context pack
        """
        self.logger.info(f"Building context pack (budget: {token_budget} tokens)")
        try:
            response = await self.client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "nexus_context_pack",
                        "arguments": {
                            "focusFiles": focus_files or [],
                            "tokenBudget": token_budget
                        }
                    }
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Context pack failed: {e}")
            raise

    async def test_run(self, framework: Optional[str] = None) -> Dict[str, Any]:
        """Run tests with framework detection.

        Args:
            framework: Test framework (auto-detect if None)

        Returns:
            Test results
        """
        self.logger.info(f"Running tests")
        try:
            response = await self.client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "nexus_test_run",
                        "arguments": {"framework": framework}
                    }
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Test run failed: {e}")
            raise

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
