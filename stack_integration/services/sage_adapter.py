"""SAGE boundary; unavailable operations fail closed."""

from typing import Any

from stack_integration.services import CapabilityUnavailableError


class SageAdapter:
    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint

    async def create_saga(
        self,
        name: str,
        steps: list[dict[str, Any]],
        compensation: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        raise CapabilityUnavailableError("SAGE runtime capability has not been admitted")

    async def execute_saga(self, saga_id: str, context: dict[str, Any]) -> dict[str, Any]:
        raise CapabilityUnavailableError("SAGE runtime capability has not been admitted")

    async def rollback_saga(self, execution_id: str) -> dict[str, Any]:
        raise CapabilityUnavailableError("SAGE runtime capability has not been admitted")

    async def close(self) -> None:
        return None
