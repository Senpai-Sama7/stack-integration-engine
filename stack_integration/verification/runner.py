"""Run admitted checks independently of the model that produced a candidate."""

from __future__ import annotations

import re
from pathlib import Path

from stack_integration.contracts.models import (
    Check,
    CheckDefinition,
    CheckStatus,
    new_id,
)
from stack_integration.providers.process import ProcessSupervisor
from stack_integration.security import redact_text
from stack_integration.storage import ArtifactStore, ControllerDatabase


class VerificationRunner:
    def __init__(
        self,
        database: ControllerDatabase,
        artifacts: ArtifactStore,
        supervisor: ProcessSupervisor | None = None,
    ):
        self.database = database
        self.artifacts = artifacts
        self.supervisor = supervisor or ProcessSupervisor()

    async def run(
        self,
        definition: CheckDefinition,
        *,
        project_id: str,
        run_id: str,
        task_id: str | None,
        candidate_hash: str,
        cwd: str | Path,
    ) -> Check:
        result = await self.supervisor.run(
            definition.command,
            cwd=cwd,
            timeout=definition.timeout_seconds,
            env=definition.environment,
        )
        combined = b"$ " + " ".join(definition.command).encode() + b"\n" + result.stdout
        if result.stderr:
            combined += b"\n[stderr]\n" + result.stderr
        artifact = self.artifacts.register_bytes(
            redact_text(combined.decode(errors="replace")).encode(),
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            producer_id="independent-verifier",
            media_type="text/plain; charset=utf-8",
            candidate_revision=candidate_hash,
        )
        tests_collected = self._tests_collected(combined.decode(errors="replace"))
        if result.timed_out or result.cancelled or result.truncated or result.launch_error:
            status = CheckStatus.ERROR
        elif definition.expects_tests and tests_collected == 0:
            status = CheckStatus.NO_TESTS
        elif result.exit_code == 0:
            status = CheckStatus.PASSED
        else:
            status = CheckStatus.FAILED
        check = Check(
            id=new_id("check"),
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            definition_id=definition.id,
            candidate_hash=candidate_hash,
            status=status,
            command=definition.command,
            exit_code=result.exit_code,
            duration_ms=result.duration_ms,
            output_artifact_id=artifact.id,
            tests_collected=tests_collected if definition.expects_tests else None,
        )
        self.database.put("check", check, actor_id="independent-verifier")
        return check

    @staticmethod
    def _tests_collected(output: str) -> int:
        patterns = [
            r"collected\s+(\d+)\s+items?",
            r"(\d+)\s+(?:passed|failed|skipped|deselected)(?:[,\s]|$)",
            r"Tests:\s+(?:\d+\s+failed,\s+)?(\d+)\s+(?:passed|total)",
        ]
        values = [
            int(match.group(1)) for pattern in patterns for match in re.finditer(pattern, output)
        ]
        return max(values, default=0)

    def required_checks_pass(self, definitions: list[CheckDefinition], checks: list[Check]) -> bool:
        by_definition = {check.definition_id: check for check in checks}
        return all(
            not definition.required
            or (
                definition.id in by_definition
                and by_definition[definition.id].status == CheckStatus.PASSED
                and (
                    not definition.expects_tests
                    or (by_definition[definition.id].tests_collected or 0) > 0
                )
            )
            for definition in definitions
        )
