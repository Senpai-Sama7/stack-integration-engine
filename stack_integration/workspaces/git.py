"""Git project registration, task worktrees, and serialized integration."""

from __future__ import annotations

import hashlib
import subprocess
import threading
from pathlib import Path

from stack_integration.contracts.models import Project


class GitError(RuntimeError):
    pass


RESERVED_WORKSPACE_NAMES = {"integration"}


def _safe_segment(name: str, *, label: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\0" in name:
        raise GitError(f"invalid {label}: {name!r}")
    if Path(name).is_absolute():
        raise GitError(f"invalid {label}: {name!r}")
    return name


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

    def task_workspace_path(
        self, project: Project, run_id: str, task_id: str, *, allow_reserved: bool = False
    ) -> Path:
        run_id = _safe_segment(run_id, label="run id")
        task_id = _safe_segment(task_id, label="task id")
        if not allow_reserved and task_id in RESERVED_WORKSPACE_NAMES:
            raise GitError(f"task id {task_id!r} is reserved for internal use")
        containment_root = (self.worktree_root / project.id / run_id).resolve()
        destination = (containment_root / task_id).resolve()
        if containment_root != destination and containment_root not in destination.parents:
            raise GitError("task workspace path escapes managed worktree root")
        return destination

    def create_task_workspace(
        self,
        project: Project,
        run_id: str,
        task_id: str,
        base_revision: str,
        *,
        allow_reserved: bool = False,
    ) -> Path:
        destination = self.task_workspace_path(
            project, run_id, task_id, allow_reserved=allow_reserved
        )
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

    def compose_task_base(self, workspace: str | Path, commits: list[str]) -> str:
        """Cherry-pick verified dependency commits onto a task's private worktree."""
        root = Path(workspace)
        for commit in commits:
            self._git(root, "cherry-pick", commit)
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

    def remove_task_workspace(
        self, project: Project, workspace: str | Path, *, force: bool = True
    ) -> None:
        path = Path(workspace).resolve()
        expected_parent = (self.worktree_root / project.id).resolve()
        if expected_parent not in path.parents:
            raise GitError("refusing to remove workspace outside managed root")
        args = ["worktree", "remove"]
        if force:
            args.append("--force")
        args.append(str(path))
        self._git(Path(project.root), *args)
