"""SQLite-backed authoritative controller state.

The controller is the only writer. State mutation and event-outbox insertion happen
in the same immediate transaction so a crash cannot publish a state that was never
committed (or commit state without recording its event).
"""

from __future__ import annotations

import builtins
import json
import shutil
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

from stack_integration.contracts.models import Event, Project, Run, Task, new_id

ModelT = TypeVar("ModelT", bound=BaseModel)

SCHEMA_VERSION = 1

MIGRATION_1 = """
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS records (
    kind TEXT NOT NULL,
    id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    run_id TEXT,
    revision INTEGER NOT NULL DEFAULT 1,
    body TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    PRIMARY KEY (kind, id)
);
CREATE INDEX IF NOT EXISTS idx_records_scope ON records(kind, project_id, run_id);
CREATE TABLE IF NOT EXISTS outbox (
    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    body TEXT NOT NULL,
    delivered_at TEXT
);
CREATE TABLE IF NOT EXISTS message_dedup (
    message_id TEXT PRIMARY KEY,
    received_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS leases (
    task_id TEXT PRIMARY KEY,
    lease_id TEXT NOT NULL UNIQUE,
    project_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    actor_id TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    fencing_token INTEGER NOT NULL,
    expires_at TEXT NOT NULL,
    heartbeat_at TEXT NOT NULL,
    revoked_at TEXT,
    body TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS counters (
    name TEXT PRIMARY KEY,
    value INTEGER NOT NULL
);
"""


class ConflictError(RuntimeError):
    """A compare-and-swap or unique ownership condition failed."""


class NotFoundError(KeyError):
    """A requested controller record does not exist."""


class ControllerDatabase:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(
            self.path, timeout=30, isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._configure()
        self.migrate()

    def _configure(self) -> None:
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA busy_timeout=30000")

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            self._connection.execute("BEGIN IMMEDIATE")
            try:
                yield self._connection
            except BaseException:
                self._connection.rollback()
                raise
            else:
                self._connection.commit()

    def migrate(self) -> None:
        with self.transaction() as connection:
            connection.executescript(MIGRATION_1)
            row = connection.execute(
                "SELECT value FROM metadata WHERE key = 'schema_version'"
            ).fetchone()
            current = int(row["value"]) if row else 0
            if current > SCHEMA_VERSION:
                raise RuntimeError(
                    f"database schema {current} is newer than supported {SCHEMA_VERSION}"
                )
            connection.execute(
                "INSERT OR REPLACE INTO metadata(key, value) VALUES('schema_version', ?)",
                (str(SCHEMA_VERSION),),
            )

    @staticmethod
    def _json(model: BaseModel) -> str:
        return model.model_dump_json()

    def put(
        self,
        kind: str,
        model: BaseModel,
        *,
        actor_id: str = "controller",
        event_type: str | None = None,
        expected_revision: int | None = None,
    ) -> int:
        body = model.model_dump(mode="json")
        record_id = str(body["id"])
        project_id = str(body.get("project_id", record_id))
        run_id = body.get("run_id")
        now = (
            body.get("created_at")
            or __import__("datetime").datetime.now(__import__("datetime").UTC).isoformat()
        )
        if not isinstance(now, str):
            now = now.isoformat()
        with self.transaction() as connection:
            row = connection.execute(
                "SELECT revision, created_at FROM records WHERE kind=? AND id=?",
                (kind, record_id),
            ).fetchone()
            current = int(row["revision"]) if row else 0
            if expected_revision is not None and current != expected_revision:
                raise ConflictError(
                    f"{kind}/{record_id} revision {current}, expected {expected_revision}"
                )
            revision = current + 1
            if "revision" in body:
                body["revision"] = revision
            payload = json.dumps(body, sort_keys=True, separators=(",", ":"))
            connection.execute(
                """INSERT INTO records(
                     kind,id,project_id,run_id,revision,body,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?)
                   ON CONFLICT(kind,id) DO UPDATE SET project_id=excluded.project_id,
                     run_id=excluded.run_id, revision=excluded.revision, body=excluded.body,
                     updated_at=excluded.updated_at""",
                (
                    kind,
                    record_id,
                    project_id,
                    run_id,
                    revision,
                    payload,
                    row["created_at"] if row else now,
                    now,
                ),
            )
            event = Event(
                id=new_id("evt"),
                project_id=project_id,
                run_id=run_id,
                aggregate_type=kind,
                aggregate_id=record_id,
                aggregate_revision=revision,
                actor_id=actor_id,
                event_type=event_type or f"{kind}.saved",
                payload={"record_id": record_id},
            )
            connection.execute(
                "INSERT INTO outbox(event_id,body) VALUES(?,?)",
                (event.id, self._json(event)),
            )
        return revision

    def get(self, kind: str, record_id: str, model_type: type[ModelT]) -> ModelT:
        row = self._connection.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", (kind, record_id)
        ).fetchone()
        if row is None:
            raise NotFoundError(f"{kind}/{record_id}")
        return model_type.model_validate_json(row["body"])

    def list(
        self,
        kind: str,
        model_type: type[ModelT],
        *,
        project_id: str | None = None,
        run_id: str | None = None,
    ) -> list[ModelT]:
        clauses = ["kind=?"]
        values: list[Any] = [kind]
        if project_id is not None:
            clauses.append("project_id=?")
            values.append(project_id)
        if run_id is not None:
            clauses.append("run_id=?")
            values.append(run_id)
        rows = self._connection.execute(
            f"SELECT body FROM records WHERE {' AND '.join(clauses)} ORDER BY created_at, id",
            values,
        ).fetchall()
        return [model_type.model_validate_json(row["body"]) for row in rows]

    def save_project(self, project: Project) -> int:
        return self.put("project", project)

    def save_run(self, run: Run, expected_revision: int | None = None) -> int:
        return self.put("run", run, expected_revision=expected_revision)

    def save_task(self, task: Task, expected_revision: int | None = None) -> int:
        return self.put("task", task, expected_revision=expected_revision)

    def next_counter(self, name: str, connection: sqlite3.Connection | None = None) -> int:
        target = connection or self._connection
        target.execute(
            "INSERT INTO counters(name,value) VALUES(?,1) "
            "ON CONFLICT(name) DO UPDATE SET value=value+1",
            (name,),
        )
        return int(target.execute("SELECT value FROM counters WHERE name=?", (name,)).fetchone()[0])

    def pending_events(self, limit: int = 100) -> builtins.list[Event]:
        rows = self._connection.execute(
            "SELECT body FROM outbox WHERE delivered_at IS NULL ORDER BY sequence LIMIT ?", (limit,)
        ).fetchall()
        return [Event.model_validate_json(row["body"]) for row in rows]

    def mark_event_delivered(self, event_id: str) -> None:
        from stack_integration.contracts.models import utc_now

        with self.transaction() as connection:
            connection.execute(
                "UPDATE outbox SET delivered_at=? WHERE event_id=? AND delivered_at IS NULL",
                (utc_now().isoformat(), event_id),
            )

    def deduplicate_message(self, message_id: str) -> bool:
        from stack_integration.contracts.models import utc_now

        with self.transaction() as connection:
            cursor = connection.execute(
                "INSERT OR IGNORE INTO message_dedup(message_id,received_at) VALUES(?,?)",
                (message_id, utc_now().isoformat()),
            )
        return cursor.rowcount == 1

    def backup(self, destination: str | Path) -> Path:
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(target) as backup_connection:
            self._connection.backup(backup_connection)
        return target

    def restore_from(self, source: str | Path) -> None:
        source_path = Path(source).expanduser().resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        self.close()
        shutil.copy2(source_path, self.path)
        self._connection = sqlite3.connect(
            self.path, timeout=30, isolation_level=None, check_same_thread=False
        )
        self._connection.row_factory = sqlite3.Row
        self._configure()
        self.migrate()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> ControllerDatabase:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
