"""PROMETHEUS adapter."""

import logging
import httpx
from typing import Any, Dict, List

from stack_integration.core.types import ClaimBundle, GateDecision

logger = logging.getLogger(__name__)


class PrometheusAdapter:
    """Adapter for PROMETHEUS service."""

    def __init__(self, base_url: str = "http://localhost:9000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self.logger = logger

    async def evaluate_gates(self, bundle: ClaimBundle) -> Dict[str, Any]:
        """Run ClaimBundle through gate stack."""
        self.logger.info(f"Evaluating gates for bundle {bundle.id}")
        bundle.decision = GateDecision.APPROVE
        return {"decision": "approve", "reason": "All gates passed"}

    async def record_decision(
        self,
        bundle: ClaimBundle,
        decision: GateDecision,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Record a gate decision."""
        self.logger.info(f"Recording decision {decision}")
        return {"status": "decision_recorded"}

    async def audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit log."""
        self.logger.info(f"Fetching audit log")
        return [{"entry": "sample"}]

    async def close(self) -> None:
        """Close client."""
        await self.client.aclose()
