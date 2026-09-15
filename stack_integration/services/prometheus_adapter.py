"""PROMETHEUS boundary; unavailable operations fail closed."""

from typing import Any

from stack_integration.core.types import ClaimBundle, GateDecision
from stack_integration.services import CapabilityUnavailableError


class PrometheusAdapter:
    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint

    async def evaluate_gates(self, bundle: ClaimBundle) -> dict[str, Any]:
        raise CapabilityUnavailableError(
            "PROMETHEUS gate transport is not configured; no approval was granted"
        )

    async def record_decision(
        self, bundle: ClaimBundle, decision: GateDecision, reason: str = ""
    ) -> dict[str, Any]:
        raise CapabilityUnavailableError("PROMETHEUS decision transport is not configured")

    async def audit_log(self, limit: int = 100) -> list[dict[str, Any]]:
        raise CapabilityUnavailableError("PROMETHEUS audit transport is not configured")

    async def close(self) -> None:
        return None
