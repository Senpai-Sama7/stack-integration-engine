"""Structured non-interactive Claude Code adapter."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from stack_integration.contracts.models import (
    CapabilityStatus,
    Provider,
    ProviderRequest,
    ProviderResult,
)
from stack_integration.providers.base import ProviderAdapter, basic_probe


class ClaudeAdapter(ProviderAdapter):
    provider = Provider.CLAUDE

    def __init__(self, executable: str = "claude", supervisor=None):
        super().__init__(executable, supervisor)

    async def probe(self):
        capability = await basic_probe(
            self.provider,
            self.executable,
            {
                "structured_result": "--output-format",
                "json_schema": "--json-schema",
                "resume": "--resume",
                "subagents": "--agents",
                "background_sessions": "--background",
                "worktree": "--worktree",
            },
            self.supervisor,
        )
        resolved = shutil.which(self.executable)
        if resolved:
            auth = await self.supervisor.run(
                [resolved, "auth", "status"], cwd=Path.cwd(), timeout=15
            )
            authenticated = False
            try:
                status = json.loads(auth.stdout)
                authenticated = auth.exit_code == 0 and status.get("loggedIn") is True
            except json.JSONDecodeError:
                pass
            capability.features["authentication"] = (
                CapabilityStatus.SUPPORTED if authenticated else CapabilityStatus.DEGRADED
            )
            if not authenticated:
                capability.status = CapabilityStatus.DEGRADED
        return capability

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        args = [
            self.executable,
            "--print",
            "--output-format",
            "json",
            "--permission-mode",
            "plan" if request.read_only else "acceptEdits",
            "--permission-prompts",
            "none",
        ]
        if request.session_id:
            args.extend(["--resume", request.session_id])
        if request.mcp_server_command:
            args.extend(
                [
                    "--strict-mcp-config",
                    "--mcp-config",
                    json.dumps(
                        {
                            "mcpServers": {
                                "stack_agent": {
                                    "command": request.mcp_server_command[0],
                                    "args": request.mcp_server_command[1:],
                                }
                            }
                        },
                        separators=(",", ":"),
                    ),
                ]
            )
        if request.output_schema is not None:
            args.extend(["--json-schema", json.dumps(request.output_schema, separators=(",", ":"))])
        args.append(request.prompt)
        process = await self.supervisor.run(
            args,
            cwd=request.project_root,
            timeout=request.timeout_seconds,
            env=request.environment,
        )
        return self.parse_result(process)

    @classmethod
    def parse_result(cls, process) -> ProviderResult:
        if process.cancelled:
            return ProviderResult(
                provider=Provider.CLAUDE,
                status="cancelled",
                error="Claude was cancelled and its process group was terminated",
                exit_code=process.exit_code,
                duration_ms=process.duration_ms,
            )
        if process.timed_out:
            return ProviderResult(
                provider=Provider.CLAUDE,
                status="timeout",
                error="Claude exceeded its task wall time",
                exit_code=process.exit_code,
                duration_ms=process.duration_ms,
            )
        if process.launch_error:
            return ProviderResult(
                provider=Provider.CLAUDE,
                status="failed",
                error=process.stderr.decode(errors="replace"),
                exit_code=None,
                duration_ms=process.duration_ms,
            )
        if process.truncated:
            return ProviderResult(
                provider=Provider.CLAUDE,
                status="protocol_error",
                error="Claude output exceeded the controller limit",
                exit_code=process.exit_code,
                duration_ms=process.duration_ms,
            )
        try:
            payload = json.loads(process.stdout.decode(errors="replace"))
            if not isinstance(payload, dict):
                raise ValueError("result is not an object")
        except (json.JSONDecodeError, ValueError) as error:
            return ProviderResult(
                provider=Provider.CLAUDE,
                status="protocol_error",
                error=f"invalid Claude JSON result: {error}",
                exit_code=process.exit_code,
                duration_ms=process.duration_ms,
            )
        successful = (
            process.exit_code == 0
            and payload.get("type") == "result"
            and payload.get("subtype") == "success"
            and not payload.get("is_error", False)
        )
        structured = payload.get("structured_output")
        if not isinstance(structured, dict):
            structured = None
        raw_usage = payload.get("usage")
        usage: dict[str, object] = dict(raw_usage) if isinstance(raw_usage, dict) else {}
        if isinstance(payload.get("total_cost_usd"), (int, float)):
            usage = {**usage, "total_cost_usd": payload["total_cost_usd"]}
        return ProviderResult(
            provider=Provider.CLAUDE,
            status="completed" if successful else "failed",
            session_id=payload.get("session_id"),
            output=str(payload.get("result", "")),
            structured_output=structured,
            error=None if successful else str(payload.get("result") or "Claude command failed"),
            exit_code=process.exit_code,
            duration_ms=process.duration_ms,
            usage=usage,
        )
