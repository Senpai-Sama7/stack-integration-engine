"""Typed compatibility workflow dispatcher.

This lightweight interface remains for callers of the original package. New
two-team workflows use :class:`CollaborationController`, while this dispatcher
ensures an unknown or failed step can never be reported as successful.
"""

from __future__ import annotations

import inspect
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from stack_integration.core.types import TaskResult, TaskStatus, WorkflowDefinition

StepHandler = Callable[[dict[str, Any], dict[str, Any]], dict[str, Any] | Awaitable[dict[str, Any]]]


class UnknownStepError(ValueError):
    pass


class Orchestrator:
    def __init__(self) -> None:
        self.handlers: dict[str, StepHandler] = {}

    def register(self, step_type: str, handler: StepHandler) -> None:
        if not step_type or step_type in self.handlers:
            raise ValueError(f"invalid or duplicate step handler: {step_type!r}")
        self.handlers[step_type] = handler

    async def execute_workflow(
        self,
        workflow: WorkflowDefinition,
        initial_state: dict[str, Any] | None = None,
    ) -> list[TaskResult]:
        state = dict(initial_state or {})
        results: list[TaskResult] = []
        for index, step in enumerate(workflow.steps):
            task_id = str(uuid.uuid4())
            step_type = step.get("type")
            started = time.monotonic()
            if not isinstance(step_type, str) or step_type not in self.handlers:
                results.append(
                    TaskResult(
                        task_id=task_id,
                        status=TaskStatus.FAILED,
                        error=f"unknown workflow step type: {step_type!r}",
                        duration_ms=(time.monotonic() - started) * 1000,
                    )
                )
                break
            try:
                value = self.handlers[step_type](step, state)
                output = await value if inspect.isawaitable(value) else value
                if not isinstance(output, dict):
                    raise TypeError("step handler must return a dictionary")
                state.update(output.get("state", {}))
                results.append(
                    TaskResult(
                        task_id=task_id,
                        status=TaskStatus.SUCCESS,
                        output={"step": index, "type": step_type, **output},
                        duration_ms=(time.monotonic() - started) * 1000,
                    )
                )
            except Exception as error:
                results.append(
                    TaskResult(
                        task_id=task_id,
                        status=TaskStatus.FAILED,
                        error=f"{type(error).__name__}: {error}",
                        duration_ms=(time.monotonic() - started) * 1000,
                    )
                )
                break
        return results
