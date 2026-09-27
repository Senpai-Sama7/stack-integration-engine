"""PLATFORM boundary; unavailable operations fail closed."""

from typing import Any

from stack_integration.services import CapabilityUnavailableError


class PlatformAdapter:
    def __init__(self, endpoint: str | None = None):
        self.endpoint = endpoint

    async def query(self, query: str, stream: bool = False) -> dict[str, Any]:
        raise CapabilityUnavailableError("PLATFORM transport is not configured")

    async def get_task_status(self, task_id: str) -> dict[str, Any]:
        raise CapabilityUnavailableError("PLATFORM transport is not configured")

    async def approve_action(self, action_id: str, approval: bool = True) -> dict[str, Any]:
        raise CapabilityUnavailableError(
            "PLATFORM decisions cannot grant controller execution authority"
        )

    async def close(self) -> None:
        return None
