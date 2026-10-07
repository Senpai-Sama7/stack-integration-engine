"""Event bus for cross-service communication."""

import inspect
import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EventType(StrEnum):
    """Types of events in the system."""

    WORKFLOW_STARTED = "workflow.started"
    WORKFLOW_COMPLETED = "workflow.completed"
    WORKFLOW_FAILED = "workflow.failed"
    TASK_STARTED = "task.started"
    TASK_COMPLETED = "task.completed"
    CLAIM_CREATED = "claim.created"
    GATE_EVALUATED = "gate.evaluated"
    APPROVAL_REQUIRED = "approval.required"


class Event(BaseModel):
    """Base event model."""

    type: EventType
    source: str
    timestamp: datetime
    payload: dict[str, Any]
    correlation_id: str | None = None


class EventBus:
    """Event bus for system-wide messaging."""

    def __init__(self, max_log_size: int = 1000) -> None:
        if max_log_size < 1:
            raise ValueError("max_log_size must be positive")
        self.subscribers: dict[str, list[Callable[[Event], Any]]] = {}
        # Bounded so a long-lived process cannot grow memory without limit.
        self.event_log: deque[Event] = deque(maxlen=max_log_size)
        self.logger = logger

    def subscribe(self, event_type: EventType, handler: Callable[[Event], Any]) -> None:
        """Subscribe a synchronous or asynchronous handler to an event type."""
        self.subscribers.setdefault(event_type, []).append(handler)
        name = getattr(handler, "__name__", repr(handler))
        self.logger.info("Subscribed %s to %s", name, event_type)

    async def publish(self, event: Event) -> None:
        """Publish an event; one failing handler never prevents the others."""
        self.event_log.append(event)
        self.logger.info("Published event %s from %s", event.type, event.source)
        for handler in list(self.subscribers.get(event.type, [])):
            try:
                outcome = handler(event)
                if inspect.isawaitable(outcome):
                    await outcome
            except Exception:
                self.logger.exception("Error in event handler")

    def get_events(
        self,
        event_type: EventType | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Query event log."""
        events = list(self.event_log)
        if event_type:
            events = [e for e in events if e.type == event_type]
        if source:
            events = [e for e in events if e.source == source]
        return events[-limit:]
