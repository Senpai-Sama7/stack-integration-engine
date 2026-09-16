"""Event bus for cross-service communication."""

import logging
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

    def __init__(self):
        self.subscribers: dict[str, list[Callable]] = {}
        self.event_log: list[Event] = []
        self.logger = logger

    def subscribe(self, event_type: EventType, handler: Callable) -> None:
        """Subscribe to an event type."""
        if event_type not in self.subscribers:
            self.subscribers[event_type] = []
        self.subscribers[event_type].append(handler)
        self.logger.info(f"Subscribed {handler.__name__} to {event_type}")

    async def publish(self, event: Event) -> None:
        """Publish an event."""
        self.event_log.append(event)
        self.logger.info(f"Published event {event.type} from {event.source}")

        # Call all subscribers
        handlers = self.subscribers.get(event.type, [])
        for handler in handlers:
            try:
                await handler(event)
            except Exception as e:
                self.logger.error(f"Error in event handler: {e}", exc_info=True)

    def get_events(
        self,
        event_type: EventType | None = None,
        source: str | None = None,
        limit: int = 100,
    ) -> list[Event]:
        """Query event log."""
        events = self.event_log
        if event_type:
            events = [e for e in events if e.type == event_type]
        if source:
            events = [e for e in events if e.source == source]
        return events[-limit:]
