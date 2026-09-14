"""Adapter for ai-agent-platform-ultimate."""

import logging
import httpx
from typing import Any, Dict, AsyncGenerator

logger = logging.getLogger(__name__)


class PlatformAdapter:
    """Adapter for communicating with PLATFORM service."""

    def __init__(self, base_url: str = "http://localhost:8000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=300.0)
        self.logger = logger

    async def query(
        self,
        query: str,
        stream: bool = False,
    ) -> Dict[str, Any] | AsyncGenerator[Dict[str, Any], None]:
        """Submit a query to the AI agent platform.

        Args:
            query: Natural language query
            stream: Whether to stream results

        Returns:
            Query results or stream of updates
        """
        self.logger.info(f"Submitting query: {query[:100]}...")
        try:
            if stream:
                return self._stream_query(query)
            else:
                response = await self.client.post(
                    "/api/agent/query",
                    json={"query": query}
                )
                response.raise_for_status()
                return response.json()
        except Exception as e:
            self.logger.error(f"Query submission failed: {e}")
            raise

    async def _stream_query(self, query: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream query results as they arrive."""
        async with self.client.stream(
            "POST",
            "/api/agent/stream",
            json={"query": query}
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    import json
                    yield json.loads(line)

    async def get_task_status(self, task_id: str) -> Dict[str, Any]:
        """Get status of a running task.

        Args:
            task_id: Task ID

        Returns:
            Task status
        """
        self.logger.info(f"Getting status for task {task_id}")
        try:
            response = await self.client.get(f"/api/tasks/{task_id}")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Task status fetch failed: {e}")
            raise

    async def approve_action(self, action_id: str, approval: bool = True) -> Dict[str, Any]:
        """Approve or reject a pending action.

        Args:
            action_id: Action ID
            approval: True to approve, False to reject

        Returns:
            Action result
        """
        self.logger.info(f"Recording approval for action {action_id}: {approval}")
        try:
            response = await self.client.post(
                f"/api/actions/{action_id}/approve",
                json={"approved": approval}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Action approval failed: {e}")
            raise

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
