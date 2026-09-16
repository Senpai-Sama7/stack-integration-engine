"""DAG admission, atomic task leasing, fencing, and recovery transitions."""

from __future__ import annotations

import sqlite3
from datetime import timedelta

from stack_integration.contracts.models import (
    Capability,
    CapabilityStatus,
    Event,
    Lease,
    Task,
    TaskStatus,
    assert_task_transition,
    new_id,
    utc_now,
)
from stack_integration.storage.database import ConflictError, ControllerDatabase, NotFoundError


class AdmissionError(ValueError):
    pass


class LeaseError(ConflictError):
    pass


class Scheduler:
    def __init__(self, database: ControllerDatabase, *, lease_seconds: int = 90):
        self.database = database
        self.lease_seconds = lease_seconds

    def admit_tasks(self, tasks: list[Task]) -> None:
        by_id = {task.id: task for task in tasks}
        if len(by_id) != len(tasks):
            raise AdmissionError("duplicate task IDs")
        if tasks:
            project_ids = {task.project_id for task in tasks}
            run_ids = {task.run_id for task in tasks}
            if len(project_ids) > 1 or len(run_ids) > 1:
                raise AdmissionError("task batch must share one project and one run")
        for task in tasks:
            try:
                self.database.get("task", task.id, Task)
            except NotFoundError:
                continue
            raise AdmissionError(f"task ID already exists in storage: {task.id}")
        existing = {
            task.id: task
            for task in self.database.list(
                "task",
                Task,
                project_id=tasks[0].project_id if tasks else None,
                run_id=tasks[0].run_id if tasks else None,
            )
        }
        all_tasks = existing | by_id
        for task in tasks:
            if task.side_effect.value != "read_only" and not task.allowed_paths:
                raise AdmissionError(
                    f"modifying task {task.id} requires an explicit allowed path scope"
                )
            missing = [
                dependency for dependency in task.dependencies if dependency not in all_tasks
            ]
            if missing:
                raise AdmissionError(f"task {task.id} has unknown dependencies: {missing}")
            for capability_id in task.required_capabilities:
                try:
                    capability = self.database.get("capability", capability_id, Capability)
                except NotFoundError as error:
                    raise AdmissionError(f"unknown capability: {capability_id}") from error
                if capability.status != CapabilityStatus.SUPPORTED:
                    raise AdmissionError(
                        f"capability {capability_id} is {capability.status.value}, not supported"
                    )
        self._assert_acyclic(all_tasks)
        for task in tasks:
            task.status = TaskStatus.READY if not task.dependencies else TaskStatus.PROPOSED
            self.database.save_task(task)
        self.refresh_ready(tasks[0].project_id if tasks else "")

    @staticmethod
    def _assert_acyclic(tasks: dict[str, Task]) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(task_id: str) -> None:
            if task_id in visiting:
                raise AdmissionError(f"task dependency cycle includes {task_id}")
            if task_id in visited:
                return
            visiting.add(task_id)
            for dependency in tasks[task_id].dependencies:
                visit(dependency)
            visiting.remove(task_id)
            visited.add(task_id)

        for task_id in tasks:
            visit(task_id)

    def refresh_ready(self, project_id: str, run_id: str | None = None) -> list[str]:
        tasks = self.database.list("task", Task, project_id=project_id, run_id=run_id)
        by_id = {task.id: task for task in tasks}
        changed: list[str] = []
        for task in tasks:
            if task.status != TaskStatus.PROPOSED:
                continue
            if all(
                by_id[dependency].status in {TaskStatus.VERIFIED, TaskStatus.INTEGRATED}
                for dependency in task.dependencies
            ):
                task.status = TaskStatus.READY
                self.database.save_task(task, expected_revision=task.revision)
                changed.append(task.id)
        return changed

    def claim(self, task_id: str, actor_id: str) -> Lease:
        now = utc_now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT body,revision FROM records WHERE kind='task' AND id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"task/{task_id}")
            task = Task.model_validate_json(row["body"])
            if task.status != TaskStatus.READY:
                raise LeaseError(f"task {task_id} is {task.status.value}, not ready")
            active = connection.execute(
                "SELECT lease_id FROM leases WHERE task_id=? AND revoked_at IS NULL", (task_id,)
            ).fetchone()
            if active is not None:
                raise LeaseError(f"task {task_id} already has an active lease")
            token = self.database.next_counter(f"fence:{task_id}", connection)
            attempt = task.attempt + 1
            lease = Lease(
                id=new_id("lease"),
                project_id=task.project_id,
                run_id=task.run_id,
                task_id=task.id,
                actor_id=actor_id,
                attempt=attempt,
                fencing_token=token,
                expires_at=now + timedelta(seconds=self.lease_seconds),
            )
            connection.execute(
                """INSERT INTO leases(task_id,lease_id,project_id,run_id,actor_id,attempt,
                   fencing_token,expires_at,heartbeat_at,revoked_at,body)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(task_id) DO UPDATE SET lease_id=excluded.lease_id,
                     project_id=excluded.project_id,run_id=excluded.run_id,
                     actor_id=excluded.actor_id,attempt=excluded.attempt,
                     fencing_token=excluded.fencing_token,expires_at=excluded.expires_at,
                     heartbeat_at=excluded.heartbeat_at,revoked_at=NULL,body=excluded.body""",
                (
                    task.id,
                    lease.id,
                    task.project_id,
                    task.run_id,
                    actor_id,
                    attempt,
                    token,
                    lease.expires_at.isoformat(),
                    lease.heartbeat_at.isoformat(),
                    None,
                    lease.model_dump_json(),
                ),
            )
            task.status = TaskStatus.LEASED
            task.attempt = attempt
            task.revision = int(row["revision"]) + 1
            connection.execute(
                "UPDATE records SET body=?,revision=?,updated_at=? WHERE kind='task' AND id=?",
                (task.model_dump_json(), task.revision, now.isoformat(), task.id),
            )
            self._append_event(connection, task, "task.leased", actor_id)
        return lease

    def heartbeat(self, task_id: str, actor_id: str, fencing_token: int) -> Lease:
        now = utc_now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT body FROM leases WHERE task_id=? AND revoked_at IS NULL", (task_id,)
            ).fetchone()
            if row is None:
                raise LeaseError("no active lease")
            lease = Lease.model_validate_json(row["body"])
            self._validate_lease(lease, actor_id, fencing_token, permit_expired=False)
            lease.heartbeat_at = now
            lease.expires_at = now + timedelta(seconds=self.lease_seconds)
            connection.execute(
                "UPDATE leases SET heartbeat_at=?,expires_at=?,body=? WHERE task_id=?",
                (now.isoformat(), lease.expires_at.isoformat(), lease.model_dump_json(), task_id),
            )
        return lease

    def transition(
        self,
        task_id: str,
        target: TaskStatus,
        *,
        actor_id: str,
        fencing_token: int | None = None,
        candidate_hash: str | None = None,
    ) -> Task:
        now = utc_now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT body,revision FROM records WHERE kind='task' AND id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"task/{task_id}")
            task = Task.model_validate_json(row["body"])
            assert_task_transition(task.status, target)
            if task.status in {TaskStatus.LEASED, TaskStatus.RUNNING}:
                lease_row = connection.execute(
                    "SELECT body FROM leases WHERE task_id=? AND revoked_at IS NULL", (task_id,)
                ).fetchone()
                if lease_row is None or fencing_token is None:
                    raise LeaseError("current fencing token required")
                lease = Lease.model_validate_json(lease_row["body"])
                self._validate_lease(lease, actor_id, fencing_token, permit_expired=False)
            if target == TaskStatus.SUBMITTED:
                if not candidate_hash:
                    raise ValueError("candidate hash is required for submission")
                task.candidate_hash = candidate_hash
            task.status = target
            task.revision = int(row["revision"]) + 1
            connection.execute(
                "UPDATE records SET body=?,revision=?,updated_at=? WHERE kind='task' AND id=?",
                (task.model_dump_json(), task.revision, now.isoformat(), task.id),
            )
            if target not in {TaskStatus.LEASED, TaskStatus.RUNNING}:
                connection.execute(
                    "UPDATE leases SET revoked_at=? WHERE task_id=? AND revoked_at IS NULL",
                    (now.isoformat(), task_id),
                )
            self._append_event(connection, task, f"task.{target.value}", actor_id)
        return task

    def reconcile_expired(self) -> list[str]:
        now = utc_now()
        rows = self.database._connection.execute(  # controller-internal query
            "SELECT task_id,lease_id,fencing_token,expires_at FROM leases "
            "WHERE revoked_at IS NULL AND expires_at < ?",
            (now.isoformat(),),
        ).fetchall()
        reconciled: list[str] = []
        for row in rows:
            task_id = row["task_id"]
            with self.database.transaction() as connection:
                lease_row = connection.execute(
                    "SELECT lease_id,fencing_token,expires_at,body FROM leases "
                    "WHERE task_id=? AND revoked_at IS NULL",
                    (task_id,),
                ).fetchone()
                if lease_row is None:
                    # Revoked (or replaced) since the scan; nothing to reconcile.
                    continue
                lease = Lease.model_validate_json(lease_row["body"])
                if (
                    lease_row["lease_id"] != row["lease_id"]
                    or int(lease_row["fencing_token"]) != int(row["fencing_token"])
                    or str(lease_row["expires_at"]) != str(row["expires_at"])
                    or lease.expires_at >= now
                ):
                    # Renewed or replaced since the scan; nothing to reconcile.
                    continue
                task_row = connection.execute(
                    "SELECT body,revision FROM records WHERE kind='task' AND id=?",
                    (task_id,),
                ).fetchone()
                if task_row is None:
                    continue
                task = Task.model_validate_json(task_row["body"])
                if task.status not in {TaskStatus.LEASED, TaskStatus.RUNNING}:
                    continue
                task.status = TaskStatus.RECONCILING
                task.revision = int(task_row["revision"]) + 1
                connection.execute(
                    "UPDATE records SET body=?,revision=?,updated_at=? WHERE kind='task' AND id=?",
                    (task.model_dump_json(), task.revision, now.isoformat(), task.id),
                )
                connection.execute(
                    """UPDATE leases SET revoked_at=?
                       WHERE task_id=? AND lease_id=? AND revoked_at IS NULL""",
                    (now.isoformat(), task.id, lease_row["lease_id"]),
                )
                self._append_event(connection, task, "task.reconciling", "controller")
            reconciled.append(task_id)
        return reconciled

    def force_terminal(
        self, task_id: str, target: TaskStatus, *, actor_id: str, reason: str
    ) -> Task:
        """Controller-only fail/cancel path used when normal worker cleanup is impossible."""
        if target not in {TaskStatus.FAILED, TaskStatus.CANCELLED}:
            raise ValueError("force_terminal only supports failed or cancelled")
        now = utc_now()
        with self.database.transaction() as connection:
            row = connection.execute(
                "SELECT body,revision FROM records WHERE kind='task' AND id=?", (task_id,)
            ).fetchone()
            if row is None:
                raise NotFoundError(f"task/{task_id}")
            task = Task.model_validate_json(row["body"])
            if task.status in {TaskStatus.INTEGRATED, TaskStatus.FAILED, TaskStatus.CANCELLED}:
                return task
            task.status = target
            task.revision = int(row["revision"]) + 1
            connection.execute(
                "UPDATE records SET body=?,revision=?,updated_at=? WHERE kind='task' AND id=?",
                (task.model_dump_json(), task.revision, now.isoformat(), task.id),
            )
            connection.execute(
                "UPDATE leases SET revoked_at=? WHERE task_id=? AND revoked_at IS NULL",
                (now.isoformat(), task.id),
            )
            event = Event(
                id=new_id("evt"),
                project_id=task.project_id,
                run_id=task.run_id,
                aggregate_type="task",
                aggregate_id=task.id,
                aggregate_revision=task.revision,
                actor_id=actor_id,
                event_type=f"task.{target.value}",
                payload={"status": target.value, "reason": reason},
            )
            connection.execute(
                "INSERT INTO outbox(event_id,body) VALUES(?,?)",
                (event.id, event.model_dump_json()),
            )
        return task

    @staticmethod
    def _validate_lease(
        lease: Lease, actor_id: str, fencing_token: int, *, permit_expired: bool
    ) -> None:
        if lease.actor_id != actor_id or lease.fencing_token != fencing_token:
            raise LeaseError("stale or foreign fencing token")
        if lease.revoked_at is not None:
            raise LeaseError("lease is revoked")
        if not permit_expired and lease.expires_at <= utc_now():
            raise LeaseError("lease has expired")

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection, task: Task, event_type: str, actor_id: str
    ) -> None:
        event = Event(
            id=new_id("evt"),
            project_id=task.project_id,
            run_id=task.run_id,
            aggregate_type="task",
            aggregate_id=task.id,
            aggregate_revision=task.revision,
            actor_id=actor_id,
            event_type=event_type,
            payload={"status": task.status.value},
        )
        connection.execute(
            "INSERT INTO outbox(event_id,body) VALUES(?,?)", (event.id, event.model_dump_json())
        )
