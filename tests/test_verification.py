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


def test_test_count_parsing_handles_real_runner_formats():
    count = VerificationRunner._tests_collected
    assert count("collected 5 items\n") == 5
    assert count("collected 1 item") == 1
    assert count("=== 12 passed, 3 failed, 1 skipped in 0.5s ===") == 12
    # Jest summaries count the passed tests, not the total (unchanged from the original).
    assert count("Tests:       2 failed, 7 passed, 9 total") == 7
    assert count("Tests: 4 passed, 4 total") == 4
    assert count("no tests ran") == 0
    assert count("") == 0


def test_test_count_parsing_cannot_be_stalled_by_hostile_output():
    """Check output is produced by candidate code. The previous unanchored `(\\d+)` was
    quadratic on a long digit run (40k digits took 13 s, so 300k would take minutes)."""
    import time

    for hostile in ("9" * 300_000, "1 " * 150_000, "Tests: " * 40_000, "1" + " " * 300_000 + "x"):
        start = time.perf_counter()
        assert VerificationRunner._tests_collected(hostile) in {0, 1}
        assert time.perf_counter() - start < 5
