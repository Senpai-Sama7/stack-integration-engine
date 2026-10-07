from datetime import UTC, datetime

import pytest

from stack_integration.core.event_bus import Event, EventBus, EventType


def event(source: str = "test") -> Event:
    return Event(
        type=EventType.TASK_STARTED,
        source=source,
        timestamp=datetime.now(UTC),
        payload={},
    )


@pytest.mark.asyncio
async def test_sync_and_async_handlers_both_run_and_failures_are_isolated():
    seen: list[str] = []

    def sync_handler(_: Event) -> None:
        seen.append("sync")

    async def async_handler(_: Event) -> None:
        seen.append("async")

    def broken(_: Event) -> None:
        raise RuntimeError("boom")

    bus = EventBus()
    bus.subscribe(EventType.TASK_STARTED, broken)
    bus.subscribe(EventType.TASK_STARTED, sync_handler)
    bus.subscribe(EventType.TASK_STARTED, async_handler)
    await bus.publish(event())
    assert seen == ["sync", "async"]


@pytest.mark.asyncio
async def test_event_log_is_bounded_and_filterable():
    bus = EventBus(max_log_size=3)
    for index in range(5):
        await bus.publish(event(source=f"s{index}"))
    assert [item.source for item in bus.get_events()] == ["s2", "s3", "s4"]
    assert [item.source for item in bus.get_events(source="s3")] == ["s3"]
    assert bus.get_events(limit=1)[0].source == "s4"
