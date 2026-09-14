"""Adapter for autonomous-sdlc-command-center."""

import logging
import httpx
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class SDLCAdapter:
    """Adapter for communicating with SDLC service."""

    def __init__(self, base_url: str = "http://localhost:8765"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self.logger = logger

    async def repo_snapshot(self, path: str) -> Dict[str, Any]:
        """Get repository snapshot.

        Args:
            path: Repository path

        Returns:
            Snapshot data
        """
        self.logger.info(f"Getting repo snapshot for {path}")
        try:
            response = await self.client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "sdlc_repo_snapshot",
                        "arguments": {"path": path}
                    }
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"SDLC snapshot failed: {e}")
            raise

    async def secret_scan(self, path: str) -> Dict[str, Any]:
        """Scan for secrets.

        Args:
            path: Repository path

        Returns:
            Scan results
        """
        self.logger.info(f"Scanning for secrets in {path}")
        try:
            response = await self.client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "sdlc_secret_scan",
                        "arguments": {"path": path}
                    }
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Secret scan failed: {e}")
            raise

    async def risk_score(self, path: str) -> Dict[str, Any]:
        """Get project risk score.

        Args:
            path: Repository path

        Returns:
            Risk score (0-100) and letter grade
        """
        self.logger.info(f"Computing risk score for {path}")
        try:
            response = await self.client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "method": "tools/call",
                    "params": {
                        "name": "sdlc_risk_score",
                        "arguments": {"path": path}
                    }
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Risk score failed: {e}")
            raise

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
