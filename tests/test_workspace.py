import os
import subprocess
from pathlib import Path

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


def _repo_with_workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "tracked.txt").write_text("base\n")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=T", "-c", "user.email=t@example.com", "commit", "-qm", "base"],
        cwd=repo,
        check=True,
    )
    manager = GitWorkspaceManager(tmp_path / "state")
    project = manager.register(repo)
    base = manager.revision(repo)
    return manager, manager.create_task_workspace(project, "run", "task", base), base, project


def _git_out(cwd, *args):
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def test_candidate_diff_is_constant_process_count_and_leaves_the_index_alone(tmp_path, monkeypatch):
    """The diff used one `git diff --no-index` process per new file (1000 files took 4 s)."""
    manager, workspace, base, _ = _repo_with_workspace(tmp_path)
    (workspace / "tracked.txt").write_text("changed\n")
    for index in range(150):
        (workspace / f"new{index}.txt").write_text(f"content {index}\n")
    status_before = _git_out(workspace, "status", "--porcelain")
    objects_before = _git_out(workspace, "count-objects", "-v")
    index_bytes = Path(_git_out(workspace, "rev-parse", "--git-path", "index").strip())
    index_bytes = (
        (workspace / index_bytes).read_bytes()
        if not index_bytes.is_absolute()
        else (index_bytes.read_bytes())
    )

    calls = []
    real_run = subprocess.run

    def counting_run(*args, **kwargs):
        calls.append(args[0])
        return real_run(*args, **kwargs)

    monkeypatch.setattr("stack_integration.workspaces.git.subprocess.run", counting_run)
    diff = manager.candidate_diff(workspace, base)
    monkeypatch.undo()

    assert len(calls) <= 6, f"{len(calls)} git processes for 150 new files"
    assert "+changed" in diff
    for index in range(150):
        assert f"b/new{index}.txt" in diff and f"+content {index}" in diff
    # Neither the real index nor the object store was touched.
    assert _git_out(workspace, "status", "--porcelain") == status_before
    assert _git_out(workspace, "count-objects", "-v") == objects_before
    now = Path(_git_out(workspace, "rev-parse", "--git-path", "index").strip())
    now = now if now.is_absolute() else workspace / now
    assert now.read_bytes() == index_bytes


def test_candidate_diff_reports_paths_it_could_not_include(tmp_path):
    manager, workspace, base, _ = _repo_with_workspace(tmp_path)
    nested = workspace / "vendored"
    nested.mkdir()
    _git_out(nested, "init", "-q")
    (workspace / "added.txt").write_text("hello\n")
    diff = manager.candidate_diff(workspace, base)
    assert "+hello" in diff
    assert "new untracked directory (not diffed): vendored/" in diff


def test_candidate_hash_streams_files_and_is_chunk_size_invariant(tmp_path, monkeypatch):
    import tracemalloc

    manager, workspace, _, _ = _repo_with_workspace(tmp_path)
    (workspace / "big.bin").write_bytes(os.urandom(48 * 1024 * 1024))
    (workspace / "small.txt").write_text("small\n")
    tracemalloc.start()
    first = manager.candidate_hash(workspace)
    peak = tracemalloc.get_traced_memory()[1]
    tracemalloc.stop()
    assert peak < 16 * 1024 * 1024, f"hashing a 48 MiB file peaked at {peak / 1e6:.0f} MB"
    monkeypatch.setattr("stack_integration.workspaces.git.HASH_CHUNK_BYTES", 7)
    assert manager.candidate_hash(workspace) == first
    (workspace / "small.txt").write_text("small!\n")
    assert manager.candidate_hash(workspace) != first


def test_concurrent_workspace_creation_and_cleanup_are_safe(tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    manager, _, base, project = _repo_with_workspace(tmp_path)

    def create(name):
        return manager.create_task_workspace(project, "concurrent", name, base)

    with ThreadPoolExecutor(max_workers=8) as pool:
        created = list(pool.map(create, [f"task{index}" for index in range(8)]))
    assert all(path.is_dir() for path in created)
    with ThreadPoolExecutor(max_workers=4) as pool:
        cleanup = pool.submit(manager.remove_run_workspaces, project, "concurrent")
        extra = pool.submit(manager.create_task_workspace, project, "other", "solo", base)
        assert len(cleanup.result()) == 8
        assert extra.result().is_dir()
