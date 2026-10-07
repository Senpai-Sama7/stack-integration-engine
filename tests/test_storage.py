from pathlib import Path

import pytest

from stack_integration.contracts.models import Project
from stack_integration.storage import ArtifactStore, ControllerDatabase
from stack_integration.storage.artifacts import ArtifactAccessError, ArtifactCorruptionError
from stack_integration.storage.database import ConflictError


def test_state_and_outbox_are_written_together(database: ControllerDatabase):
    project = Project(id="p1", root="/tmp/p1", git_common_dir="/tmp/p1/.git")
    database.save_project(project)
    stored = database.get("project", "p1", Project)
    events = database.pending_events()
    assert stored.id == "p1"
    assert events[-1].aggregate_id == "p1"


def test_compare_and_swap_rejects_stale_revision(database: ControllerDatabase):
    project = Project(id="p1", root="/tmp/p1", git_common_dir="/tmp/p1/.git")
    database.save_project(project)
    database.put("project", project, expected_revision=1)
    with pytest.raises(ConflictError):
        database.put("project", project, expected_revision=1)


def test_artifact_integrity_and_project_scope(
    artifacts: ArtifactStore, database: ControllerDatabase
):
    artifact = artifacts.register_bytes(
        b"evidence",
        project_id="p1",
        run_id="r1",
        producer_id="verifier",
    )
    assert artifacts.read(artifact.id, project_id="p1") == b"evidence"
    with pytest.raises(ArtifactAccessError):
        artifacts.read(artifact.id, project_id="p2")
    (artifacts.root / artifact.relative_path).write_bytes(b"tampered")
    with pytest.raises(ArtifactCorruptionError):
        artifacts.read(artifact.id, project_id="p1")


def test_backup_is_readable(tmp_path: Path, database: ControllerDatabase):
    database.save_project(Project(id="p1", root="/tmp/p1", git_common_dir="/tmp/p1/.git"))
    target = database.backup(tmp_path / "backup.db")
    with ControllerDatabase(target) as restored:
        assert restored.get("project", "p1", Project).id == "p1"


def test_update_advances_updated_at_but_keeps_created_at(database: ControllerDatabase):
    project = Project(id="p1", root="/tmp/p1", git_common_dir="/tmp/p1/.git")
    database.save_project(project)
    first = database._fetchone("SELECT created_at,updated_at FROM records WHERE id='p1'")
    database.save_project(project)
    second = database._fetchone("SELECT created_at,updated_at FROM records WHERE id='p1'")
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] > first["updated_at"]
    assert second["updated_at"] != second["created_at"]


def test_restore_replaces_live_state_through_backup_api(
    tmp_path: Path, database: ControllerDatabase
):
    database.save_project(Project(id="p1", root="/tmp/p1", git_common_dir="/tmp/p1/.git"))
    snapshot = database.backup(tmp_path / "snapshot.db")
    database.save_project(Project(id="p2", root="/tmp/p2", git_common_dir="/tmp/p2/.git"))
    database.restore_from(snapshot)
    assert database.exists("project", "p1")
    assert not database.exists("project", "p2")
    # The live connection keeps working after the restore.
    database.save_project(Project(id="p3", root="/tmp/p3", git_common_dir="/tmp/p3/.git"))
    with ControllerDatabase(database.path) as reopened:
        assert reopened.exists("project", "p3")
        assert not reopened.exists("project", "p2")


def test_backup_refuses_to_overwrite_live_database(database: ControllerDatabase):
    with pytest.raises(ValueError, match="differ"):
        database.backup(database.path)


def test_concurrent_identical_artifacts_do_not_collide(artifacts: ArtifactStore):
    from concurrent.futures import ThreadPoolExecutor

    def write(_: int):
        return artifacts.register_bytes(b"same", project_id="p1", run_id="r1", producer_id="x")

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(write, range(32)))
    assert {item.content_hash for item in results} == {results[0].content_hash}
    directory = (artifacts.root / results[0].relative_path).parent
    assert [path.name for path in directory.iterdir()] == [results[0].content_hash[2:]]
    assert artifacts.read(results[0].id, project_id="p1") == b"same"


def _task(task_id: str, run_id: str, status):
    from stack_integration.contracts.models import Provider, Task

    return Task(
        id=task_id,
        project_id="p1",
        run_id=run_id,
        description=task_id,
        owner_provider=Provider.CODEX,
        status=status,
    )


def test_status_counts_aggregate_per_run_without_loading_records(database: ControllerDatabase):
    from stack_integration.contracts.models import TaskStatus

    for index, status in enumerate(
        [TaskStatus.READY, TaskStatus.READY, TaskStatus.FAILED, TaskStatus.VERIFIED]
    ):
        database.save_task(_task(f"a{index}", "run-a", status))
    database.save_task(_task("b0", "run-b", TaskStatus.RUNNING))
    database.save_project(Project(id="p1", root="/tmp/p1", git_common_dir="/tmp/p1/.git"))
    assert database.status_counts("task") == {
        "run-a": {"ready": 2, "failed": 1, "verified": 1},
        "run-b": {"running": 1},
    }
    assert database.status_counts("review") == {}


def test_status_counts_fall_back_when_sqlite_lacks_json_functions(
    database: ControllerDatabase, monkeypatch
):
    import sqlite3

    from stack_integration.contracts.models import TaskStatus

    database.save_task(_task("a0", "run-a", TaskStatus.READY))
    database.save_task(_task("a1", "run-a", TaskStatus.FAILED))
    expected = database.status_counts("task")
    real = database._fetchall

    def without_json(sql, parameters=()):
        if "json_extract" in sql:
            raise sqlite3.OperationalError("no such function: json_extract")
        return real(sql, parameters)

    monkeypatch.setattr(database, "_fetchall", without_json)
    assert database.status_counts("task") == expected == {"run-a": {"ready": 1, "failed": 1}}
