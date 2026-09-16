from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

import pytest

from stack_integration.contracts.models import Provider, SideEffect, Task, TaskStatus, utc_now
from stack_integration.controller.scheduler import AdmissionError, LeaseError, Scheduler
from stack_integration.storage import ControllerDatabase


def task(task_id: str, dependencies=None):
    return Task(
        id=task_id,
        project_id="p1",
        run_id="r1",
        description=task_id,
        owner_provider=Provider.CODEX,
        dependencies=dependencies or [],
    )


def test_dependency_cycle_is_rejected(database: ControllerDatabase):
    scheduler = Scheduler(database)
    with pytest.raises(AdmissionError, match="cycle"):
        scheduler.admit_tasks([task("a", ["b"]), task("b", ["a"])])


def test_modifying_task_requires_explicit_scope(database: ControllerDatabase):
    scheduler = Scheduler(database)
    value = task("write")
    value.side_effect = SideEffect.WORKTREE_WRITE
    with pytest.raises(AdmissionError, match="explicit allowed path"):
        scheduler.admit_tasks([value])


def test_two_claimers_get_exactly_one_lease(database: ControllerDatabase):
    scheduler = Scheduler(database)
    scheduler.admit_tasks([task("a")])

    def claim(actor):
        try:
            return scheduler.claim("a", actor)
        except LeaseError:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        leases = list(pool.map(claim, ["codex", "claude"]))
    assert sum(item is not None for item in leases) == 1


def test_stale_fencing_token_is_rejected(database: ControllerDatabase):
    scheduler = Scheduler(database)
    scheduler.admit_tasks([task("a")])
    lease = scheduler.claim("a", "codex")
    with pytest.raises(LeaseError, match="stale"):
        scheduler.transition(
            "a",
            TaskStatus.RUNNING,
            actor_id="codex",
            fencing_token=lease.fencing_token + 1,
        )


def test_expired_writer_enters_reconciliation(database: ControllerDatabase):
    scheduler = Scheduler(database)
    scheduler.admit_tasks([task("a")])
    lease = scheduler.claim("a", "codex")
    lease.expires_at = utc_now() - timedelta(seconds=1)
    database._connection.execute(
        "UPDATE leases SET expires_at=?,body=? WHERE task_id='a'",
        (lease.expires_at.isoformat(), lease.model_dump_json()),
    )
    assert scheduler.reconcile_expired() == ["a"]
    assert database.get("task", "a", Task).status == TaskStatus.RECONCILING


def test_admission_rejects_existing_task_ids(database: ControllerDatabase):
    scheduler = Scheduler(database)
    scheduler.admit_tasks([task("a")])
    with pytest.raises(AdmissionError, match="already exist"):
        scheduler.admit_tasks([task("a")])
