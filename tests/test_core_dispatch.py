import pytest

from stack_integration.core.orchestrator import Orchestrator
from stack_integration.core.types import TaskStatus, WorkflowDefinition


@pytest.mark.asyncio
async def test_unknown_step_fails_closed():
    result = await Orchestrator().execute_workflow(
        WorkflowDefinition(id="w", name="w", description="w", steps=[{"type": "invented"}])
    )
    assert result[0].status == TaskStatus.FAILED
    assert "unknown" in (result[0].error or "")


@pytest.mark.asyncio
async def test_registered_step_executes():
    orchestrator = Orchestrator()
    orchestrator.register("known", lambda step, state: {"value": 42})
    result = await orchestrator.execute_workflow(
        WorkflowDefinition(id="w", name="w", description="w", steps=[{"type": "known"}])
    )
    assert result[0].status == TaskStatus.SUCCESS
    assert result[0].output["value"] == 42
