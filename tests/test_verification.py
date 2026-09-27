from pathlib import Path

import pytest

from stack_integration.contracts.models import CheckDefinition, CheckStatus
from stack_integration.verification import VerificationRunner


@pytest.mark.asyncio
async def test_no_collected_tests_does_not_pass(database, artifacts, tmp_path: Path):
    runner = VerificationRunner(database, artifacts)
    check = await runner.run(
        CheckDefinition(
            id="tests",
            name="tests",
            command=["python3", "-c", "print('collected 0 items')"],
            expects_tests=True,
        ),
        project_id="p1",
        run_id="r1",
        task_id="t1",
        candidate_hash="candidate",
        cwd=tmp_path,
    )
    assert check.status == CheckStatus.NO_TESTS


@pytest.mark.asyncio
async def test_nonzero_check_fails_with_artifact(database, artifacts, tmp_path: Path):
    runner = VerificationRunner(database, artifacts)
    check = await runner.run(
        CheckDefinition(
            id="bad",
            name="bad",
            command=["python3", "-c", "raise SystemExit(7)"],
        ),
        project_id="p1",
        run_id="r1",
        task_id="t1",
        candidate_hash="candidate",
        cwd=tmp_path,
    )
    assert check.status == CheckStatus.FAILED
    assert artifacts.read(check.output_artifact_id, project_id="p1").startswith(b"$ python3")
