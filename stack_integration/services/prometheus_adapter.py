"""Adapter for prometheus-stack."""

import logging
import httpx
from typing import Any, Dict, List

from stack_integration.core.types import ClaimBundle, GateDecision

logger = logging.getLogger(__name__)


class PrometheusAdapter:
    """Adapter for communicating with PROMETHEUS service."""

    def __init__(self, base_url: str = "http://localhost:9000"):
        self.base_url = base_url
        self.client = httpx.AsyncClient(base_url=base_url, timeout=30.0)
        self.logger = logger

    async def evaluate_gates(self, bundle: ClaimBundle) -> Dict[str, Any]:
        """Run ClaimBundle through gate stack.

        Args:
            bundle: Claim bundle to evaluate

        Returns:
            Gate evaluation result
        """
        self.logger.info(f"Evaluating gates for bundle {bundle.id}")
        try:
            response = await self.client.post(
                "/api/gates/evaluate",
                json=bundle.model_dump()
            )
            response.raise_for_status()
            result = response.json()
            bundle.decision = GateDecision(result["decision"])
            bundle.reason = result.get("reason", "")
            return result
        except Exception as e:
            self.logger.error(f"Gate evaluation failed: {e}")
            raise

    async def record_decision(
        self,
        bundle: ClaimBundle,
        decision: GateDecision,
        reason: str = "",
    ) -> Dict[str, Any]:
        """Record a gate decision.

        Args:
            bundle: Claim bundle
            decision: Decision made
            reason: Reason for decision

        Returns:
            Recorded decision
        """
        self.logger.info(f"Recording decision {decision} for bundle {bundle.id}")
        try:
            response = await self.client.post(
                "/api/decisions",
                json={
                    "bundle_id": bundle.id,
                    "decision": decision.value,
                    "reason": reason
                }
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Recording decision failed: {e}")
            raise

    async def audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get audit log.

        Args:
            limit: Maximum number of entries

        Returns:
            Audit log entries
        """
        self.logger.info(f"Fetching audit log (limit: {limit})")
        try:
            response = await self.client.get(
                f"/api/audit",
                params={"limit": limit}
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error(f"Audit log fetch failed: {e}")
            raise

    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
