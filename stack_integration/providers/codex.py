"""Structured `codex exec` adapter."""

from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from stack_integration.contracts.models import (
    Capability,
    CapabilityStatus,
    Provider,
    ProviderRequest,
    ProviderResult,
)
from stack_integration.providers.base import ProviderAdapter


class CodexAdapter(ProviderAdapter):
    provider = Provider.CODEX

    def __init__(self, executable: str = "codex", supervisor=None):
        super().__init__(executable, supervisor)

    async def probe(self):
        resolved = shutil.which(self.executable)
        if resolved is None:
            return Capability(
                id="provider.codex",
                provider=self.provider,
                executable=self.executable,
                status=CapabilityStatus.UNSUPPORTED,
                detail="executable not found",
            )
        version, top_help, exec_help, auth = await asyncio.gather(
            self.supervisor.run([resolved, "--version"], cwd=Path.cwd(), timeout=15),
            self.supervisor.run([resolved, "--help"], cwd=Path.cwd(), timeout=15),
            self.supervisor.run([resolved, "exec", "--help"], cwd=Path.cwd(), timeout=15),
            self.supervisor.run([resolved, "login", "status"], cwd=Path.cwd(), timeout=15),
        )
        top = (top_help.stdout + top_help.stderr).decode(errors="replace")
        execute = (exec_help.stdout + exec_help.stderr).decode(errors="replace")
        authenticated = auth.exit_code == 0 and b"Logged in" in (auth.stdout + auth.stderr)
        features = {
            "structured_events": CapabilityStatus.SUPPORTED
            if "--json" in execute
            else CapabilityStatus.UNSUPPORTED,
            "output_schema": CapabilityStatus.SUPPORTED
            if "--output-schema" in execute
            else CapabilityStatus.UNSUPPORTED,
            "resume": CapabilityStatus.SUPPORTED
            if "resume" in execute
            else CapabilityStatus.UNSUPPORTED,
            "worktree": CapabilityStatus.SUPPORTED
            if "--worktree" in execute
            else CapabilityStatus.UNSUPPORTED,
            "app_server": CapabilityStatus.SUPPORTED
            if "app-server" in top
            else CapabilityStatus.UNSUPPORTED,
            "authentication": CapabilityStatus.SUPPORTED
            if authenticated
            else CapabilityStatus.DEGRADED,
        }
        return Capability(
            id="provider.codex",
            provider=self.provider,
            executable=resolved,
            version=(version.stdout or version.stderr).decode(errors="replace").strip(),
            status=(
                CapabilityStatus.SUPPORTED
                if all(
                    features[name] == CapabilityStatus.SUPPORTED
                    for name in ("structured_events", "output_schema", "authentication")
                )
                else CapabilityStatus.DEGRADED
            ),
            features=features,
        )

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        args = [
            self.executable,
            "--cd",
            request.project_root,
            "--sandbox",
            "read-only" if request.read_only else "workspace-write",
        ]
        if request.mcp_server_command:
            args.extend(
                [
                    "--config",
                    f"mcp_servers.stack_agent.command={json.dumps(request.mcp_server_command[0])}",
                    "--config",
                    "mcp_servers.stack_agent.args=" + json.dumps(request.mcp_server_command[1:]),
                ]
            )
        args.append("exec")
        if request.session_id:
            args.extend(["resume", request.session_id])
        args.append("--json")
        schema_path: str | None = None
        try:
            if request.output_schema is not None:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".json", prefix="stack-agent-schema-", delete=False
                ) as schema_file:
                    json.dump(request.output_schema, schema_file)
                    schema_path = schema_file.name
                args.extend(["--output-schema", schema_path])
            args.append(request.prompt)
            process = await self.supervisor.run(
                args,
                cwd=request.project_root,
                timeout=request.timeout_seconds,
                env=request.environment,
            )
        finally:
            if schema_path:
                Path(schema_path).unlink(missing_ok=True)
        return self.parse_result(process)

    @classmethod
    def parse_result(cls, process) -> ProviderResult:
        if process.cancelled:
            return ProviderResult(
                provider=Provider.CODEX,
                status="cancelled",
                error="Codex was cancelled and its process group was terminated",
                exit_code=process.exit_code,
                duration_ms=process.duration_ms,
            )
        if process.timed_out:
            return ProviderResult(
                provider=Provider.CODEX,
                status="timeout",
                error="Codex exceeded its task wall time",
                exit_code=process.exit_code,
                duration_ms=process.duration_ms,
            )
        if process.launch_error:
            return ProviderResult(
                provider=Provider.CODEX,
                status="failed",
                error=process.stderr.decode(errors="replace"),
                exit_code=None,
                duration_ms=process.duration_ms,
            )
        if process.truncated:
            return ProviderResult(
                provider=Provider.CODEX,
                status="protocol_error",
                error="Codex output exceeded the controller limit",
                exit_code=process.exit_code,
                duration_ms=process.duration_ms,
            )
        events: list[dict] = []
        try:
            for line in process.stdout.decode(errors="replace").splitlines():
                if line.strip():
                    parsed = json.loads(line)
                    if not isinstance(parsed, dict):
                        raise ValueError("event is not an object")
                    events.append(parsed)
        except (json.JSONDecodeError, ValueError) as parse_error:
            return ProviderResult(
                provider=Provider.CODEX,
                status="protocol_error",
                error=f"invalid Codex JSONL: {parse_error}",
                exit_code=process.exit_code,
                duration_ms=process.duration_ms,
            )
        thread_id = next(
            (event.get("thread_id") for event in events if event.get("type") == "thread.started"),
            None,
        )
        completed = next(
            (event for event in reversed(events) if event.get("type") == "turn.completed"), None
        )
        failed = next(
            (event for event in reversed(events) if event.get("type") in {"turn.failed", "error"}),
            None,
        )
        messages = [
            event.get("item", {}).get("text", "")
            for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "agent_message"
        ]
        status = "completed" if process.exit_code == 0 and completed is not None else "failed"
        result_error: str | None = None
        if status != "completed":
            result_error = (
                (failed or {}).get("message")
                or process.stderr.decode(errors="replace").strip()
                or "Codex exited without a terminal completion event"
            )
        structured = None
        if messages:
            try:
                value = json.loads(messages[-1])
                structured = value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                pass
        return ProviderResult(
            provider=Provider.CODEX,
            status=status,
            session_id=thread_id,
            output="\n".join(messages),
            structured_output=structured,
            error=result_error,
            exit_code=process.exit_code,
            duration_ms=process.duration_ms,
            usage=(completed or {}).get("usage", {}),
        )
