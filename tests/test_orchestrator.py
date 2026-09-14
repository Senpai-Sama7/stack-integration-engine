"""Tests for orchestrator."""

import pytest
from stack_integration.core.orchestrator import Orchestrator
from stack_integration.core.types import WorkflowDefinition, TaskStatus


@pytest.mark.asyncio
async def test_execute_workflow():
    """Test workflow execution."""
    orchestrator = Orchestrator()
    workflow = WorkflowDefinition(
        id="test-workflow",
        name="Test Workflow",
        description="A test workflow",
        steps=[
            {"type": "sdlc_scan", "name": "Scan project"},
            {"type": "nexus_analysis", "name": "Analyze code"},
        ],
    )

    results = await orchestrator.execute_workflow(workflow)

    assert len(results) == 2
    assert results[0].status == TaskStatus.SUCCESS
    assert results[1].status == TaskStatus.SUCCESS
