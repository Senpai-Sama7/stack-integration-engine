"""Adapter for sage (ADOS v3.0)."""

import logging
import httpx
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SageAdapter:
    """Adapter for communicating with SAGE service."""

    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=60.0)
        self.logger = logger

    async def create_saga(
        self,
        name: str,
        steps: List[Dict[str, Any]],
        compensation: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """Create a Saga workflow.

        Args:
            name: Saga name
            steps: Execution steps
            compensation: Compensation steps for rollback

        Returns:
            Created saga
        """
        self.logger.info(f"Creating saga: {name}")
        try:
            response = await self.client.post(
                "/api/sagas",
                json={
                    "name": name,
                    "steps": steps,
                    "compensation": compensation or []
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Saga creation failed: {e}")
            raise

    async def execute_saga(self, saga_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a saga.

        Args:
            saga_id: Saga ID
            context: Execution context

        Returns:
            Execution result
        """
        self.logger.info(f"Executing saga {saga_id}")
        try:
            response = await self.client.post(
                f"/api/sagas/{saga_id}/execute",
                json={"context": context}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Saga execution failed: {e}")
            raise

    async def rollback_saga(self, execution_id: str) -> Dict[str, Any]:
        """Rollback a saga execution.

        Args:
            execution_id: Execution ID

        Returns:
            Rollback result
        """
        self.logger.info(f"Rolling back execution {execution_id}")
        try:
            response = await self.client.post(
                f"/api/executions/{execution_id}/rollback"
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Saga rollback failed: {e}")
            raise

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
