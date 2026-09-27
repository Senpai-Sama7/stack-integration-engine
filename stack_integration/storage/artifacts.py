"""Project-scoped, content-addressed artifact storage."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path

from stack_integration.contracts.models import Artifact, new_id
from stack_integration.storage.database import ControllerDatabase


class ArtifactCorruptionError(RuntimeError):
    pass


class ArtifactAccessError(PermissionError):
    pass


class ArtifactStore:
    def __init__(self, root: str | Path, database: ControllerDatabase):
        self.root = Path(root).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.database = database

    def register_bytes(
        self,
        content: bytes,
        *,
        project_id: str,
        run_id: str | None,
        producer_id: str,
        media_type: str = "application/octet-stream",
        task_id: str | None = None,
        base_revision: str | None = None,
        candidate_revision: str | None = None,
    ) -> Artifact:
        digest = hashlib.sha256(content).hexdigest()
        relative = Path(project_id) / digest[:2] / digest[2:]
        target = self.root / relative
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if target.exists():
            if target.read_bytes() != content:
                raise ArtifactCorruptionError(f"hash collision or corruption: {digest}")
        else:
            temporary = target.with_suffix(f".tmp-{os.getpid()}")
            temporary.write_bytes(content)
            temporary.chmod(0o600)
            os.replace(temporary, target)
        artifact = Artifact(
            id=new_id("art"),
            project_id=project_id,
            run_id=run_id,
            task_id=task_id,
            producer_id=producer_id,
            content_hash=digest,
            size=len(content),
            media_type=media_type,
            relative_path=str(relative),
            base_revision=base_revision,
            candidate_revision=candidate_revision,
        )
        self.database.put(
            "artifact", artifact, actor_id=producer_id, event_type="artifact.registered"
        )
        return artifact

    def register_text(
        self,
        text: str,
        *,
        project_id: str,
        run_id: str | None,
        producer_id: str,
        task_id: str | None = None,
        base_revision: str | None = None,
        candidate_revision: str | None = None,
    ) -> Artifact:
        return self.register_bytes(
            text.encode(),
            project_id=project_id,
            run_id=run_id,
            producer_id=producer_id,
            media_type="text/plain; charset=utf-8",
            task_id=task_id,
            base_revision=base_revision,
            candidate_revision=candidate_revision,
        )

    def read(self, artifact_id: str, *, project_id: str) -> bytes:
        artifact = self.database.get("artifact", artifact_id, Artifact)
        if artifact.project_id != project_id:
            raise ArtifactAccessError("cross-project artifact access denied")
        target = self.root / artifact.relative_path
        try:
            content = target.read_bytes()
        except FileNotFoundError as error:
            raise ArtifactCorruptionError(f"artifact content missing: {artifact.id}") from error
        actual = hashlib.sha256(content).hexdigest()
        if actual != artifact.content_hash or len(content) != artifact.size:
            raise ArtifactCorruptionError(f"artifact integrity check failed: {artifact.id}")
        return content

    def manifest(self, project_id: str, run_id: str | None = None) -> list[Artifact]:
        return self.database.list("artifact", Artifact, project_id=project_id, run_id=run_id)
