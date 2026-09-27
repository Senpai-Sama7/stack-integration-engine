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
