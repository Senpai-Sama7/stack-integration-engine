"""SDLC command-center adapter using its JSON CLI contract."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

from stack_integration.providers.process import ProcessSupervisor

READ_ONLY_COMMANDS = {
    "snapshot",
    "release-readiness",
    "plugin-preflight",
    "read",
    "read-batch",
    "tree",
    "search",
    "secret-scan",
    "languages",
    "deps",
    "git-history",
    "risk",
    "doctor",
    "changes",
    "audit",
    "metrics",
    "sbom",
}


class SdlcToolAdapter:
    def __init__(
        self,
        executable: str = "sdlc",
        supervisor: ProcessSupervisor | None = None,
        source_script: str | Path | None = None,
    ):
        self.executable = executable
        self.supervisor = supervisor or ProcessSupervisor(output_limit_bytes=5 * 1024 * 1024)
        self.source_script = (
            Path(
                source_script
                or os.environ.get("SDLC_CLI_SCRIPT")
                or (Path.home() / "Projects/MCPs/autonomous-sdlc-command-center/mcp/sdlc_cli.py")
            )
            .expanduser()
            .resolve()
        )
        self._command: list[str] | None = None

    async def _resolve_command(self) -> tuple[list[str] | None, str]:
        resolved = shutil.which(self.executable)
        candidates: list[list[str]] = [[resolved]] if resolved else []
        if self.source_script.is_file():
            candidates.append(["python3", str(self.source_script)])
        failures: list[str] = []
        for candidate in candidates:
            result = await self.supervisor.run(
                [*candidate, "--version"], cwd=Path.cwd(), timeout=15
            )
            if result.exit_code == 0:
                self._command = candidate
                return candidate, result.stdout.decode(errors="replace").strip()
            failures.append((result.stderr or result.stdout).decode(errors="replace").strip())
        return None, "; ".join(item for item in failures if item) or "sdlc executable not found"

    async def probe(self) -> dict[str, Any]:
        command, detail = await self._resolve_command()
        if command is None:
            return {"status": "unsupported", "detail": detail}
        return {
            "status": "supported",
            "command": command,
            "version": detail,
            "installed_entrypoint_healthy": len(command) == 1,
        }

    async def run_read_only(
        self,
        command: str,
        *,
        project_root: str | Path,
        options: list[str] | None = None,
        timeout: float = 120,
    ) -> dict[str, Any]:
        if command not in READ_ONLY_COMMANDS:
            raise PermissionError(f"SDLC command is not admitted as read-only: {command}")
        if self._command is None:
            resolved, detail = await self._resolve_command()
            if resolved is None:
                raise RuntimeError(detail)
        args = [*(self._command or []), command]
        if command != "doctor":
            args.extend(["--path", str(Path(project_root).resolve())])
        args.extend(options or [])
        result = await self.supervisor.run(args, cwd=project_root, timeout=timeout)
        if result.truncated:
            raise RuntimeError("SDLC output exceeded controller limit")
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise RuntimeError("SDLC emitted invalid JSON") from error
        if result.exit_code not in {0, 1}:
            raise RuntimeError(result.stderr.decode(errors="replace") or "SDLC command failed")
        if not isinstance(payload, dict):
            raise RuntimeError("SDLC output must be a JSON object")
        payload["_controller_exit_code"] = result.exit_code
        return payload
