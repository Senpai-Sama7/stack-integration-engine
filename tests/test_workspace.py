import subprocess

import pytest

from stack_integration.workspaces import GitWorkspaceManager
from stack_integration.workspaces.git import GitError


def test_root_scope_allows_changes_and_user_tree_is_untouched(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "tracked.txt").write_text("base\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "base",
        ],
        cwd=repo,
        check=True,
    )
    (repo / "user-dirty.txt").write_text("preserve\n")
    manager = GitWorkspaceManager(tmp_path / "state")
    project = manager.register(repo)
    base = manager.revision(repo)
    workspace = manager.create_task_workspace(project, "run", "task", base)
    (workspace / "new.txt").write_text("candidate\n")
    assert manager.enforce_scope(workspace, base, ["."]) == ["new.txt"]
    assert (repo / "user-dirty.txt").read_text() == "preserve\n"
    with pytest.raises(GitError, match="outside task scope"):
        manager.enforce_scope(workspace, base, [])
