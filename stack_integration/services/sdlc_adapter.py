"""Compatibility wrapper around the verified SDLC JSON CLI."""

from stack_integration.tools import SdlcToolAdapter


class SDLCAdapter:
    def __init__(self, executable: str = "sdlc"):
        self.adapter = SdlcToolAdapter(executable)

    async def repo_snapshot(self, path: str) -> dict:
        return await self.adapter.run_read_only("snapshot", project_root=path)

    async def secret_scan(self, path: str) -> dict:
        return await self.adapter.run_read_only("secret-scan", project_root=path)

    async def risk_score(self, path: str) -> dict:
        return await self.adapter.run_read_only("risk", project_root=path)

    async def close(self) -> None:
        return None
