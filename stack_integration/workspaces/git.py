"""Git project registration, task worktrees, and serialized integration."""

from __future__ import annotations

import hashlib
import subprocess
import threading
from pathlib import Path

from stack_integration.contracts.models import Project


class GitError(RuntimeError):
    pass


class GitWorkspaceManager:
    def __init__(self, state_root: str | Path):
        self.state_root = Path(state_root).expanduser().resolve()
        self.worktree_root = self.state_root / "worktrees"
        self.worktree_root.mkdir(parents=True, exist_ok=True)
        self._integration_lock = threading.Lock()

    @staticmethod
    def _git(root: Path, *args: str, check: bool = True) -> str:
        result = subprocess.run(
            ["git", *args], cwd=root, text=True, capture_output=True, check=False
        )
        if check and result.returncode != 0:
            raise GitError(result.stderr.strip() or result.stdout.strip())
        return result.stdout.strip()

    def register(self, root: str | Path) -> Project:
        path = Path(root).expanduser().resolve()
        top = Path(self._git(path, "rev-parse", "--show-toplevel")).resolve()
        common_raw = self._git(top, "rev-parse", "--git-common-dir")
        common = (
            (top / common_raw).resolve() if not Path(common_raw).is_absolute() else Path(common_raw)
        )
        project_id = "prj_" + hashlib.sha256(str(common).encode()).hexdigest()[:20]
        return Project(id=project_id, root=str(top), git_common_dir=str(common))

    def revision(self, root: str | Path, reference: str = "HEAD") -> str:
        return self._git(Path(root), "rev-parse", "--verify", f"{reference}^{{commit}}")

    def dirty_paths(self, root: str | Path) -> list[str]:
        output = self._git(Path(root), "status", "--porcelain=v1", "-z")
        return [item[3:] for item in output.split("\0") if len(item) >= 4]

    def create_task_workspace(
        self, project: Project, run_id: str, task_id: str, base_revision: str
    ) -> Path:
        destination = self.worktree_root / project.id / run_id / task_id
        if destination.exists():
            raise GitError(f"workspace already exists: {destination}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        self._git(
            Path(project.root),
            "worktree",
            "add",
            "--detach",
            str(destination),
            base_revision,
        )
        return destination

    def changed_paths(self, workspace: str | Path, base_revision: str) -> list[str]:
        output = self._git(
            Path(workspace), "diff", "--name-only", "--no-renames", base_revision, "--"
        )
        untracked = self._git(
            Path(workspace), "ls-files", "--others", "--exclude-standard"
        ).splitlines()
        return sorted(set(output.splitlines()) | set(untracked))

    def enforce_scope(
        self, workspace: str | Path, base_revision: str, allowed_paths: list[str]
    ) -> list[str]:
        changed = self.changed_paths(workspace, base_revision)
        allowed = tuple(Path(item).as_posix().strip("/") for item in allowed_paths)
        violations = [
            path
            for path in changed
            if "." not in allowed
            and (
                not allowed
                or not any(path == root or path.startswith(root + "/") for root in allowed)
            )
        ]
        if violations:
            raise GitError(f"workspace changed paths outside task scope: {violations}")
        return changed

    def candidate_hash(self, workspace: str | Path) -> str:
        root = Path(workspace)
        head = self.revision(root)
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--"],
            cwd=root,
            capture_output=True,
            check=True,
        ).stdout
        untracked = self._git(root, "ls-files", "--others", "--exclude-standard").splitlines()
        digest = hashlib.sha256()
        digest.update(head.encode())
        digest.update(diff)
        for relative in sorted(untracked):
            digest.update(relative.encode())
            digest.update((root / relative).read_bytes())
        return digest.hexdigest()

    def commit_candidate(self, workspace: str | Path, message: str) -> str:
        root = Path(workspace)
        self._git(root, "add", "--all")
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False)
        if result.returncode == 0:
            raise GitError("candidate contains no changes")
        self._git(
            root,
            "-c",
            "user.name=Stack Integration Controller",
            "-c",
            "user.email=stack-agent@localhost",
            "commit",
            "-m",
            message,
        )
        return self.revision(root)

    def integrate_commit(
        self, integration_workspace: str | Path, candidate_commit: str, expected_head: str
    ) -> str:
        root = Path(integration_workspace)
        with self._integration_lock:
            current = self.revision(root)
            if current != expected_head:
                raise GitError(
                    f"integration base changed: expected {expected_head}, found {current}"
                )
            self._git(root, "cherry-pick", candidate_commit)
            return self.revision(root)

    def remove_task_workspace(self, project: Project, workspace: str | Path) -> None:
        path = Path(workspace).resolve()
        expected_parent = (self.worktree_root / project.id).resolve()
        if expected_parent not in path.parents:
            raise GitError("refusing to remove workspace outside managed root")
        self._git(Path(project.root), "worktree", "remove", str(path))
