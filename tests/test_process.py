import asyncio
import sys

import pytest

from stack_integration.providers.process import ProcessSupervisor


@pytest.mark.asyncio
async def test_output_is_bounded_while_process_is_drained(tmp_path):
    supervisor = ProcessSupervisor(output_limit_bytes=1024)
    result = await supervisor.run(
        [sys.executable, "-c", "print('x' * 1000000)"],
        cwd=tmp_path,
        timeout=10,
    )
    assert result.exit_code == 0
    assert result.truncated is True
    assert len(result.stdout) <= 1024


@pytest.mark.asyncio
async def test_cancellation_terminates_process_group_and_returns_state(tmp_path):
    supervisor = ProcessSupervisor()
    task = asyncio.create_task(
        supervisor.run(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=tmp_path,
            timeout=120,
        )
    )
    await asyncio.sleep(0.05)
    task.cancel()
    result = await task
    assert result.cancelled is True
    assert result.exit_code is not None


@pytest.mark.asyncio
async def test_launch_error_is_structured(tmp_path):
    result = await ProcessSupervisor().run(
        ["definitely-not-an-executable-stack-agent"], cwd=tmp_path, timeout=1
    )
    assert result.launch_error is True
    assert result.exit_code is None


@pytest.mark.asyncio
async def test_large_stdin_is_delivered(tmp_path):
    payload = b"y" * (512 * 1024)
    result = await ProcessSupervisor().run(
        [sys.executable, "-c", "import sys; print(len(sys.stdin.buffer.read()))"],
        cwd=tmp_path,
        timeout=10,
        stdin=payload,
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == str(len(payload)).encode()


@pytest.mark.asyncio
async def test_child_ignoring_stdin_cannot_bypass_wall_time(tmp_path):
    result = await ProcessSupervisor(kill_grace=0.5).run(
        [sys.executable, "-c", "import time; time.sleep(60)"],
        cwd=tmp_path,
        timeout=0.5,
        stdin=b"z" * (4 * 1024 * 1024),
    )
    assert result.timed_out is True
    assert result.duration_ms < 10_000


@pytest.mark.asyncio
async def test_descendant_holding_pipes_cannot_hang_supervisor(tmp_path):
    script = (
        "import subprocess, sys; "
        "subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); "
        "print('leader done')"
    )
    result = await ProcessSupervisor(drain_timeout=0.5).run(
        [sys.executable, "-c", script], cwd=tmp_path, timeout=30
    )
    assert result.exit_code == 0
    assert result.timed_out is False
    assert b"leader done" in result.stdout
    assert result.lingering_descendants is True
    assert result.duration_ms < 10_000


@pytest.mark.asyncio
async def test_removed_environment_is_not_inherited(tmp_path, monkeypatch):
    monkeypatch.setenv("STACK_AGENT_TEST_SECRET", "leak")
    result = await ProcessSupervisor().run(
        [sys.executable, "-c", "import os; print(os.environ.get('STACK_AGENT_TEST_SECRET'))"],
        cwd=tmp_path,
        timeout=10,
        remove_env=["STACK_AGENT_TEST_SECRET"],
    )
    assert result.stdout.strip() == b"None"
