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
