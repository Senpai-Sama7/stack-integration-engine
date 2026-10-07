"""Git project registration, task worktrees, and serialized integration."""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from pathlib import Path

from stack_integration.contracts.models import Project


class GitError(RuntimeError):
    pass


RESERVED_WORKSPACE_NAMES = {"integration"}
INTEGRATION_REF_PREFIX = "refs/heads/stack-agent/"


def _safe_segment(name: str, *, label: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\\" in name or "\0" in name:
        raise GitError(f"invalid {label}: {name!r}")
    if Path(name).is_absolute():
        raise GitError(f"invalid {label}: {name!r}")
    return name


def _repository_path(subdirectory: str, relative: str) -> str:
    """Translate a project-relative path into a repository-relative one."""
    normalized = Path(relative).as_posix().strip("/")
    if normalized in {"", "."}:
        normalized = "."
    if subdirectory in {"", "."}:
        return normalized
    return subdirectory if normalized == "." else f"{subdirectory}/{normalized}"


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

    @staticmethod
    def _git_bytes(root: Path, *args: str, ok_codes: tuple[int, ...] = (0,)) -> bytes:
        result = subprocess.run(["git", *args], cwd=root, capture_output=True, check=False)
        if result.returncode not in ok_codes:
            raise GitError(result.stderr.decode(errors="replace").strip())
        return result.stdout

    def register(self, root: str | Path) -> Project:
        """Register a repository root or a subdirectory of one (monorepo package).

        Worktrees of one repository share a project identity; a subdirectory is a
        distinct project whose scope paths, checks, and provider working directory are
        relative to that subdirectory.
        """
        path = Path(root).expanduser().resolve()
        if not path.is_dir():
            raise GitError(f"project path is not a directory: {path}")
        top = Path(self._git(path, "rev-parse", "--show-toplevel")).resolve()
        common_raw = self._git(top, "rev-parse", "--git-common-dir")
        common = (
            (top / common_raw).resolve() if not Path(common_raw).is_absolute() else Path(common_raw)
        )
        subdirectory = path.relative_to(top).as_posix() if path != top else "."
        identity = str(common) if subdirectory == "." else f"{common}\0{subdirectory}"
        project_id = "prj_" + hashlib.sha256(identity.encode()).hexdigest()[:20]
        return Project(
            id=project_id, root=str(top), git_common_dir=str(common), subdirectory=subdirectory
        )

    @staticmethod
    def project_directory(project: Project, workspace: str | Path) -> Path:
        """The project's working directory inside a worktree of its repository."""
        base = Path(workspace)
        return base if project.subdirectory == "." else base / project.subdirectory

    def revision(self, root: str | Path, reference: str = "HEAD") -> str:
        return self._git(Path(root), "rev-parse", "--verify", f"{reference}^{{commit}}")

    def path_exists_at(self, root: str | Path, revision: str, relative: str) -> bool:
        if relative in {"", "."}:
            return True
        result = subprocess.run(
            ["git", "cat-file", "-e", f"{revision}:{relative}"],
            cwd=Path(root),
            capture_output=True,
            check=False,
        )
        return result.returncode == 0

    def dirty_paths(self, root: str | Path) -> list[str]:
        output = self._git_bytes(Path(root), "status", "--porcelain=v1", "-z").decode(
            errors="replace"
        )
        paths: list[str] = []
        entries = iter(output.split("\0"))
        for item in entries:
            if len(item) < 4:
                continue
            paths.append(item[3:])
            if item[0] in {"R", "C"}:
                # Renames/copies carry the original path as a separate NUL field.
                next(entries, None)
        return paths

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
        """Repository-relative paths changed since ``base_revision`` (tracked + untracked)."""
        output = self._git(
            Path(workspace), "diff", "--name-only", "--no-renames", base_revision, "--"
        )
        return sorted(set(output.splitlines()) | set(self._untracked(Path(workspace))))

    def _untracked(self, root: Path) -> list[str]:
        output = self._git_bytes(root, "ls-files", "-z", "--others", "--exclude-standard")
        return [item for item in output.decode(errors="surrogateescape").split("\0") if item]

    def enforce_scope(
        self,
        workspace: str | Path,
        base_revision: str,
        allowed_paths: list[str],
        *,
        subdirectory: str = ".",
    ) -> list[str]:
        changed = self.changed_paths(workspace, base_revision)
        allowed = tuple(_repository_path(subdirectory, item) for item in allowed_paths)
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

    def candidate_diff(self, workspace: str | Path, base_revision: str) -> str:
        """A reviewable diff of every candidate change, including new untracked files.

        ``git diff BASE`` alone omits untracked files, so a task that only creates files
        would otherwise present an empty diff to its reviewer. Untracked files are
        rendered with ``--no-index`` against /dev/null without touching the index.
        """
        root = Path(workspace)
        parts = [self._git_bytes(root, "diff", "--no-ext-diff", "--no-color", base_revision, "--")]
        for relative in sorted(self._untracked(root)):
            parts.append(
                self._git_bytes(
                    root,
                    "diff",
                    "--no-ext-diff",
                    "--no-color",
                    "--no-index",
                    "--",
                    os.devnull,
                    relative,
                    ok_codes=(0, 1),
                )
            )
        return b"".join(parts).decode(errors="replace")

    def candidate_hash(self, workspace: str | Path) -> str:
        root = Path(workspace)
        head = self.revision(root)
        diff = self._git_bytes(root, "diff", "--binary", "HEAD", "--")
        digest = hashlib.sha256()
        digest.update(head.encode())
        digest.update(diff)
        for relative in sorted(self._untracked(root)):
            target = root / relative
            digest.update(b"\0path\0" + relative.encode(errors="surrogateescape"))
            if target.is_symlink():
                # Hash the link itself; following it could read outside the workspace.
                digest.update(b"\0symlink\0" + os.readlink(target).encode(errors="replace"))
            elif target.is_dir():
                # Untracked nested repositories are listed as directories.
                digest.update(b"\0directory\0")
            elif target.is_file():
                digest.update(b"\0file\0")
                digest.update(target.read_bytes())
        return digest.hexdigest()

    _COMMIT_IDENTITY = (
        "-c",
        "user.name=Stack Integration Controller",
        "-c",
        "user.email=stack-agent@localhost",
        "-c",
        "commit.gpgsign=false",
    )

    def commit_candidate(self, workspace: str | Path, message: str) -> str:
        root = Path(workspace)
        self._git(root, "add", "--all")
        result = subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=root, check=False)
        if result.returncode == 0:
            raise GitError("candidate contains no changes")
        self._git(root, *self._COMMIT_IDENTITY, "commit", "--no-verify", "-m", message)
        return self.revision(root)

    def compose_task_base(self, workspace: str | Path, commits: list[str]) -> str:
        """Cherry-pick verified dependency commits onto a task's private worktree."""
        root = Path(workspace)
        for commit in commits:
            self._cherry_pick(root, commit)
        return self.revision(root)

    def _cherry_pick(self, root: Path, commit: str) -> None:
        try:
            self._git(root, *self._COMMIT_IDENTITY, "cherry-pick", commit)
        except GitError as error:
            # Leave the worktree clean so a later inspection or retry starts sane.
            self._git(root, "cherry-pick", "--abort", check=False)
            raise GitError(f"cherry-pick of {commit} failed: {error}") from error

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
            self._cherry_pick(root, candidate_commit)
            return self.revision(root)

    def publish_integration_ref(self, project: Project, run_id: str, commit: str) -> str:
        """Point ``stack-agent/<run_id>`` at an integrated commit.

        The branch keeps the verified result reachable (worktree HEADs alone are
        detached) without touching the operator's checked-out branch or working tree.
        """
        reference = INTEGRATION_REF_PREFIX + _safe_segment(run_id, label="run id")
        self._git(Path(project.root), "check-ref-format", reference)
        self._git(
            Path(project.root),
            "update-ref",
            "-m",
            f"stack-agent: integrate {run_id}",
            reference,
            commit,
        )
        return reference

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

    def remove_run_workspaces(self, project: Project, run_id: str) -> list[str]:
        """Remove every managed worktree of one run and prune Git's worktree records."""
        run_root = (
            self.worktree_root / project.id / _safe_segment(run_id, label="run id")
        ).resolve()
        removed: list[str] = []
        if run_root.is_dir():
            for workspace in sorted(item for item in run_root.iterdir() if item.is_dir()):
                self.remove_task_workspace(project, workspace)
                removed.append(workspace.name)
            if not any(run_root.iterdir()):
                run_root.rmdir()
        self._git(Path(project.root), "worktree", "prune")
        return removed
