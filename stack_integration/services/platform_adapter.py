"""PLATFORM adapter."""

import logging
import httpx
from typing import Any, Dict

logger = logging.getLogger(__name__)


class PlatformAdapter:
    """Adapter for PLATFORM service."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=300.0)
        self.logger = logger

    async def query(self, query: str, stream: bool = False) -> Dict[str, Any]:
        """Submit a query."""
        self.logger.info(f"Submitting query: {query[:50]}...")
        return {"status": "query_received", "task_id": "task-123"}

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get task status."""
        self.logger.info(f"Getting status for task {task_id}")
        return {"status": "running", "progress": 50}

    async def approve_action(self, action_id: str, approval: bool = True) -> Dict[str, Any]:
        """Approve or reject an action."""
        self.logger.info(f"Recording approval for action {action_id}: {approval}")
        return {"status": "approved" if approval else "rejected"}

    async def close(self) -> None:
        """Close client."""
        await self.client.aclose()
