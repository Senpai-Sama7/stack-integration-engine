"""End-to-end controller flows exercised with scripted (non-model) providers."""

import asyncio
import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from stack_integration.config import Settings
from stack_integration.contracts.models import (
    Capability,
    CapabilityStatus,
    CheckDefinition,
    Finding,
    Message,
    Project,
    Provider,
    ProviderRequest,
    ProviderResult,
    Run,
    RunStatus,
    Task,
    TaskStatus,
    new_id,
)
from stack_integration.controller import CollaborationController
from stack_integration.controller.runtime import topological_order
from stack_integration.controller.scheduler import AdmissionError
from stack_integration.providers.base import ProviderAdapter
from stack_integration.workspaces import GitWorkspaceManager

Behavior = Callable[[ProviderRequest], Any]


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def make_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    path.mkdir()
    git(path, "init", "-q")
    for relative, content in (files or {"README.md": "fixture\n"}).items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git(path, "add", ".")
    git(path, "commit", "-qm", "base")
    return path


def approve(coverage: list[str]) -> dict[str, Any]:
    return {"verdict": "approve", "summary": "ok", "requirement_coverage": coverage, "findings": []}


def work(changed: list[str] | None = None) -> dict[str, Any]:
    return {
        "summary": "done",
        "changed_paths": changed or [],
        "requirements_addressed": [],
        "known_limitations": [],
    }


class ScriptedAdapter(ProviderAdapter):
    """Builder writes ``<task_id>.txt`` when modifying; reviewer approves everything."""

    def __init__(
        self,
        provider: Provider,
        log: list[ProviderRequest],
        *,
        builder: Behavior | None = None,
        reviewer: Behavior | None = None,
    ):
        super().__init__("fake")
        self.provider = provider
        self.log = log
        self.builder = builder
        self.reviewer = reviewer

    async def probe(self) -> Capability:
        return Capability(
            id=f"provider.{self.provider.value}",
            provider=self.provider,
            executable="fake",
            status=CapabilityStatus.SUPPORTED,
        )

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.log.append(request)
        if request.role.value == "reviewer":
            behavior = self.reviewer or (lambda _: approve(["REQ-1"]))
        else:
            behavior = self.builder or self.default_builder
        structured = behavior(request)
        if asyncio.iscoroutine(structured):
            structured = await structured
        return ProviderResult(
            provider=self.provider,
            status="completed",
            session_id=f"{self.provider.value}-{len(self.log)}",
            output=json.dumps(structured),
            structured_output=structured,
            exit_code=0,
            duration_ms=1,
        )

    @staticmethod
    def default_builder(request: ProviderRequest) -> dict[str, Any]:
        if request.read_only:
            return work()
        filename = f"{request.task_id}.txt"
        (Path(request.project_root) / filename).write_text(f"{request.task_id}\n")
        return work([filename])


def controller_for(
    tmp_path: Path,
    log: list[ProviderRequest],
    *,
    builder: Behavior | None = None,
    reviewer: Behavior | None = None,
) -> CollaborationController:
    providers = {
        provider: ScriptedAdapter(provider, log, builder=builder, reviewer=reviewer)
        for provider in Provider
    }
    controller = CollaborationController(Settings.load(tmp_path / "state"), providers=providers)
    controller.dispatch_poll_seconds = 0.05
    return controller


NOOP_CHECK = [CheckDefinition(id="noop", name="noop", command=["true"])]


def diagnostics(controller: CollaborationController, run: Run) -> str:
    tasks = controller.database.list("task", Task, project_id=run.project_id, run_id=run.id)
    findings = controller.database.list(
        "finding", Finding, project_id=run.project_id, run_id=run.id
    )
    return json.dumps(
        {
            "tasks": {task.id: task.status.value for task in tasks},
            "findings": [finding.statement for finding in findings],
        },
        indent=2,
    )


@pytest.mark.asyncio
async def test_transitive_dependencies_and_integration_branch(tmp_path: Path):
    """A modifying task behind a read-only review must still build on the upstream
    modification, and the review must see it. The verified result is published on a
    stack-agent/<run> branch without touching the operator's checkout."""
    repo = make_repo(tmp_path / "repo")
    head_before = git(repo, "rev-parse", "HEAD")
    seen: dict[str, bool] = {}

    def builder(request: ProviderRequest) -> dict[str, Any]:
        root = Path(request.project_root)
        seen[request.task_id] = (root / "build.txt").exists()
        if request.read_only:
            return work()
        filename = f"{request.task_id}.txt"
        (root / filename).write_text(request.task_id)
        return work([filename])

    log: list[ProviderRequest] = []
    controller = controller_for(tmp_path, log, builder=builder)
    try:
        run = controller.create_run(repo, "chain", ["REQ-1"], checks=NOOP_CHECK)
        # Dependents are listed before their prerequisites on purpose.
        controller.add_tasks(
            run.id,
            [
                {
                    "id": "polish",
                    "description": "write polish",
                    "provider": "codex",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["polish.txt"],
                    "dependencies": ["review"],
                },
                {
                    "id": "review",
                    "description": "review build",
                    "provider": "claude",
                    "dependencies": ["build"],
                },
                {
                    "id": "build",
                    "description": "write build",
                    "provider": "codex",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["build.txt"],
                },
            ],
        )
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.COMPLETED, diagnostics(controller, run)
        assert seen == {"build": False, "review": True, "polish": True}
        assert completed.integration_ref == f"refs/heads/stack-agent/{run.id}"
        assert git(repo, "rev-parse", completed.integration_ref) == completed.integration_commit
        tree = git(repo, "ls-tree", "--name-only", completed.integration_ref).splitlines()
        assert {"build.txt", "polish.txt", "README.md"} <= set(tree)
        assert git(repo, "rev-parse", "HEAD") == head_before
        assert not (repo / "build.txt").exists()
        report = controller.run_report(run.id)
        assert report["summary"]["tasks"] == {"integrated": 3}
        assert report["run"]["integration_commit"] == completed.integration_commit
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_reviewer_diff_includes_new_untracked_files(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    log: list[ProviderRequest] = []
    controller = controller_for(tmp_path, log)
    try:
        run = controller.create_run(repo, "new file", ["REQ-1"], checks=NOOP_CHECK)
        controller.add_tasks(
            run.id,
            [
                {
                    "id": "create",
                    "description": "create a file",
                    "provider": "codex",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["create.txt"],
                }
            ],
        )
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.COMPLETED, diagnostics(controller, run)
        review_prompt = next(item.prompt for item in log if item.role.value == "reviewer")
        assert "create.txt" in review_prompt
        assert "+create" in review_prompt
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_retry_prompt_carries_review_feedback_and_operator_steering(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    verdicts = iter(["request_changes", "approve"])

    def reviewer(_: ProviderRequest) -> dict[str, Any]:
        verdict = next(verdicts)
        findings = (
            [{"severity": "medium", "statement": "handle the empty-input edge case"}]
            if verdict == "request_changes"
            else []
        )
        return {
            "verdict": verdict,
            "summary": "s",
            "requirement_coverage": ["REQ-1"],
            "findings": findings,
        }

    log: list[ProviderRequest] = []
    controller = controller_for(tmp_path, log, reviewer=reviewer)
    try:
        run = controller.create_run(repo, "analyze", ["REQ-1"])
        controller.add_tasks(run.id, [{"id": "t1", "description": "analyze", "provider": "codex"}])
        controller.database.put(
            "message",
            Message(
                id=new_id("msg"),
                project_id=run.project_id,
                run_id=run.id,
                sender_id="local-operator",
                recipient_id="broadcast",
                purpose="status",
                body="Prefer the smallest possible change.",
            ),
            actor_id="local-operator",
        )
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.COMPLETED, diagnostics(controller, run)
        builder_prompts = [item.prompt for item in log if item.role.value == "builder"]
        assert len(builder_prompts) == 2
        assert "Prefer the smallest possible change." in builder_prompts[0]
        assert "handle the empty-input edge case" not in builder_prompts[0]
        assert "previous review verdict: request_changes" in builder_prompts[1]
        assert "handle the empty-input edge case" in builder_prompts[1]
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_dependents_dispatch_without_waiting_for_unrelated_slow_task(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    dependent_started = asyncio.Event()
    order: list[str] = []

    async def builder(request: ProviderRequest) -> dict[str, Any]:
        order.append(f"start:{request.task_id}")
        if request.task_id == "after-fast":
            dependent_started.set()
        if request.task_id == "slow":
            # With wave-based dispatch this deadlocks until the timeout fires.
            await asyncio.wait_for(dependent_started.wait(), timeout=10)
        order.append(f"end:{request.task_id}")
        return work()

    log: list[ProviderRequest] = []
    controller = controller_for(tmp_path, log, builder=builder)
    try:
        run = controller.create_run(repo, "parallel", ["REQ-1"])
        controller.add_tasks(
            run.id,
            [
                {"id": "slow", "description": "slow", "provider": "codex"},
                {"id": "fast", "description": "fast", "provider": "claude"},
                {
                    "id": "after-fast",
                    "description": "dependent",
                    "provider": "codex",
                    "dependencies": ["fast"],
                },
            ],
        )
        completed = await asyncio.wait_for(controller.execute_run(run.id), timeout=30)
        assert completed.status == RunStatus.COMPLETED, diagnostics(controller, run)
        assert order.index("start:after-fast") < order.index("end:slow")
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_operator_cancel_stops_in_flight_work_promptly(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    started = asyncio.Event()

    async def builder(_: ProviderRequest) -> dict[str, Any]:
        started.set()
        await asyncio.sleep(60)
        return work()

    log: list[ProviderRequest] = []
    controller = controller_for(tmp_path, log, builder=builder)
    try:
        run = controller.create_run(repo, "cancel", ["REQ-1"])
        controller.add_tasks(run.id, [{"id": "t1", "description": "hang", "provider": "codex"}])
        execution = asyncio.create_task(controller.execute_run(run.id))
        await asyncio.wait_for(started.wait(), timeout=10)
        current = controller.database.get("run", run.id, Run)
        current.status = RunStatus.CANCELLED
        controller.database.save_run(current, expected_revision=current.revision)
        controller.cancel_task("t1")
        finished = await asyncio.wait_for(execution, timeout=10)
        assert finished.status == RunStatus.CANCELLED
        assert controller.database.get("task", "t1", Task).status == TaskStatus.CANCELLED
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_malformed_reviewer_output_abstains_instead_of_crashing(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")

    def reviewer(_: ProviderRequest) -> dict[str, Any]:
        return {
            "verdict": "LGTM",
            "summary": "s",
            "requirement_coverage": "REQ-1",
            "findings": [{"severity": "urgent", "statement": 3}],
        }

    log: list[ProviderRequest] = []
    controller = controller_for(tmp_path, log, reviewer=reviewer)
    try:
        run = controller.create_run(repo, "analyze", ["REQ-1"])
        controller.add_tasks(run.id, [{"id": "t1", "description": "analyze", "provider": "codex"}])
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.BLOCKED
        task = controller.database.get("task", "t1", Task)
        assert task.status == TaskStatus.CHANGES_REQUESTED
        findings = controller.database.list(
            "finding", Finding, project_id=run.project_id, run_id=run.id
        )
        assert any("malformed" in item.statement for item in findings)
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_subdirectory_project_scopes_paths_and_checks(tmp_path: Path):
    repo = make_repo(
        tmp_path / "repo",
        {"README.md": "root\n", "packages/app/app.txt": "app\n", "other/x.txt": "x\n"},
    )
    log: list[ProviderRequest] = []
    controller = controller_for(tmp_path, log)
    try:
        run = controller.create_run(
            repo / "packages" / "app",
            "edit app",
            ["REQ-1"],
            checks=[
                CheckDefinition(
                    id="cwd",
                    name="runs in the project directory",
                    command=["test", "-f", "app.txt"],
                )
            ],
        )
        project = controller.database.get("project", run.project_id, Project)
        assert project.subdirectory == "packages/app"
        root_project = controller.register_project(repo)
        assert root_project.id != project.id
        controller.add_tasks(
            run.id,
            [
                {
                    "id": "edit",
                    "description": "edit",
                    "provider": "claude",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["edit.txt"],
                }
            ],
        )
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.COMPLETED, diagnostics(controller, run)
        builder = next(item for item in log if item.role.value == "builder")
        assert builder.project_root.endswith(os.path.join("edit", "packages", "app"))
        tree = git(repo, "ls-tree", "-r", "--name-only", completed.integration_ref or "")
        assert "packages/app/edit.txt" in tree.splitlines()
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_subdirectory_project_rejects_writes_outside_it(tmp_path: Path):
    repo = make_repo(tmp_path / "repo", {"pkg/a.txt": "a\n", "outside.txt": "o\n"})

    def builder(request: ProviderRequest) -> dict[str, Any]:
        (Path(request.project_root).parent / "outside.txt").write_text("escaped\n")
        return work(["../outside.txt"])

    log: list[ProviderRequest] = []
    controller = controller_for(tmp_path, log, builder=builder)
    try:
        run = controller.create_run(repo / "pkg", "edit", ["REQ-1"], checks=NOOP_CHECK)
        controller.add_tasks(
            run.id,
            [
                {
                    "id": "edit",
                    "description": "edit",
                    "provider": "codex",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["."],
                }
            ],
        )
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.FAILED
        findings = controller.database.list(
            "finding", Finding, project_id=run.project_id, run_id=run.id
        )
        assert any("outside task scope" in item.statement for item in findings)
    finally:
        controller.close()


def test_plan_validation_fails_closed(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    controller = controller_for(tmp_path, [])
    try:
        run = controller.create_run(repo, "validate", ["REQ-1"], scope_paths=["src"])
        with pytest.raises(ValueError, match="unknown fields"):
            controller.add_tasks(
                run.id, [{"id": "t", "description": "d", "dependencys": ["other"]}]
            )
        with pytest.raises(ValueError, match="outside the run scope"):
            controller.add_tasks(
                run.id,
                [
                    {
                        "id": "t",
                        "description": "d",
                        "side_effect": "worktree_write",
                        "allowed_paths": ["docs"],
                    }
                ],
            )
        with pytest.raises(ValueError, match="normalized"):
            controller.add_tasks(
                run.id, [{"id": "t", "description": "d", "allowed_paths": ["src/../.."]}]
            )
        with pytest.raises(AdmissionError, match="not admitted"):
            controller.add_tasks(
                run.id,
                [{"id": "t", "description": "d", "side_effect": "push", "allowed_paths": ["src"]}],
            )
        with pytest.raises(AdmissionError, match="invalid task ID"):
            controller.add_tasks(run.id, [{"id": "../escape", "description": "d"}])
        with pytest.raises(ValueError, match="normalized"):
            controller.create_run(repo, "bad", ["REQ-1"], scope_paths=["/etc"])
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_operator_requeue_and_cleanup(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    controller = controller_for(tmp_path, [])
    try:
        run = controller.create_run(repo, "recover", ["REQ-1"])
        controller.add_tasks(run.id, [{"id": "t1", "description": "analyze", "provider": "codex"}])
        with pytest.raises(ValueError, match="can be requeued"):
            controller.requeue_task("t1")
        lease = controller.scheduler.claim("t1", "someone")
        controller.scheduler.transition(
            "t1", TaskStatus.RUNNING, actor_id="someone", fencing_token=lease.fencing_token
        )
        controller.scheduler.force_terminal(
            "t1", TaskStatus.FAILED, actor_id="controller", reason="x"
        )
        with pytest.raises(ValueError, match="can be requeued"):
            controller.requeue_task("t1")
        with pytest.raises(ValueError, match="only completed"):
            controller.cleanup_run(run.id)

        second = controller.create_run(repo, "recover", ["REQ-1"])
        controller.add_tasks(
            second.id, [{"id": "t2", "description": "analyze", "provider": "codex"}]
        )
        controller.scheduler.transition("t2", TaskStatus.BLOCKED, actor_id="controller")
        assert controller.requeue_task("t2").status == TaskStatus.READY
        completed = await controller.execute_run(second.id)
        assert completed.status == RunStatus.COMPLETED
        workspace = Path(controller.database.get("task", "t2", Task).workspace or "")
        assert workspace.is_dir()
        assert controller.cleanup_run(second.id) == ["t2"]
        assert not workspace.exists()
        assert str(workspace) not in git(repo, "worktree", "list")
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_exhausted_budget_blocks_with_recorded_reason(tmp_path: Path):
    from stack_integration.contracts.models import Budget

    repo = make_repo(tmp_path / "repo")
    controller = controller_for(tmp_path, [])
    try:
        run = controller.create_run(repo, "budget", ["REQ-1"], budget=Budget(reported_cost_usd=0))
        controller.add_tasks(run.id, [{"id": "t1", "description": "analyze", "provider": "codex"}])
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.BLOCKED
        findings = controller.database.list(
            "finding", Finding, project_id=run.project_id, run_id=run.id
        )
        assert any("budget" in item.statement for item in findings)
        assert controller.database.get("task", "t1", Task).status == TaskStatus.READY
    finally:
        controller.close()


def test_topological_order_is_stable_and_detects_cycles():
    def task(task_id: str, dependencies: list[str]) -> Task:
        return Task(
            id=task_id,
            project_id="p",
            run_id="r",
            description=task_id,
            owner_provider=Provider.CODEX,
            dependencies=dependencies,
        )

    ordered = topological_order([task("c", ["b"]), task("x", []), task("b", ["a"]), task("a", [])])
    assert [item.id for item in ordered] == ["x", "a", "b", "c"]
    with pytest.raises(ValueError, match="cycle"):
        topological_order([task("a", ["b"]), task("b", ["a"])])


def test_candidate_hash_tolerates_untracked_directories_and_symlinks(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    manager = GitWorkspaceManager(tmp_path / "state")
    project = manager.register(repo)
    workspace = manager.create_task_workspace(project, "run", "task", manager.revision(repo))
    nested = workspace / "nested"
    nested.mkdir()
    git(nested, "init", "-q")
    (workspace / "link").symlink_to("/definitely/not/a/real/target")
    first = manager.candidate_hash(workspace)
    (workspace / "link").unlink()
    (workspace / "link").symlink_to("/another/target")
    assert manager.candidate_hash(workspace) != first


def test_policy_file_is_loaded_from_state_root(tmp_path: Path):
    state = tmp_path / "state"
    state.mkdir()
    (state / "policy.json").write_text(
        json.dumps({"scheduling": {"max_task_attempts": 4, "lease_seconds": 120}})
    )
    controller = CollaborationController(Settings.load(state))
    try:
        assert controller.policy.policy.max_task_attempts == 4
        assert controller.scheduler.lease_seconds == 120
    finally:
        controller.close()
    (state / "policy.json").write_text(json.dumps({"scheduling": {"heartbeat_seconds": 500}}))
    with pytest.raises(ValueError, match="heartbeat"):
        CollaborationController(Settings.load(state))
    (state / "policy.json").write_text(json.dumps({"schedulng": {}}))
    with pytest.raises(ValueError, match="unknown policy sections"):
        CollaborationController(Settings.load(state))


@pytest.mark.asyncio
async def test_verified_run_integrates_even_after_cost_budget_is_spent(tmp_path: Path):
    """A budget stops model dispatch, not integration: a cumulative cost budget must not
    leave a fully verified run permanently unfinishable."""
    from stack_integration.contracts.models import Budget, Usage

    repo = make_repo(tmp_path / "repo")
    controller = controller_for(tmp_path, [])
    try:
        run = controller.create_run(
            repo, "budget", ["REQ-1"], budget=Budget(reported_cost_usd=1.0), checks=NOOP_CHECK
        )
        controller.add_tasks(
            run.id,
            [
                {
                    "id": "write",
                    "description": "write",
                    "provider": "codex",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["write.txt"],
                }
            ],
        )
        await controller.execute_task("write")
        assert controller.database.get("task", "write", Task).status == TaskStatus.VERIFIED
        controller.database.put(
            "usage",
            Usage(
                id=new_id("usage"),
                project_id=run.project_id,
                run_id=run.id,
                session_id="s",
                reported_cost_usd=5.0,
                source="test",
            ),
        )
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.COMPLETED, diagnostics(controller, run)
        assert completed.integration_ref
    finally:
        controller.close()


def test_scope_enforcement_handles_non_ascii_paths(tmp_path: Path):
    repo = make_repo(tmp_path / "repo", {"src/café.txt": "v1\n"})
    manager = GitWorkspaceManager(tmp_path / "state")
    project = manager.register(repo)
    base = manager.revision(repo)
    workspace = manager.create_task_workspace(project, "run", "task", base)
    (workspace / "src" / "café.txt").write_text("v2\n")
    (workspace / "src" / "naïve.txt").write_text("new\n")
    assert manager.enforce_scope(workspace, base, ["src"]) == ["src/café.txt", "src/naïve.txt"]


def test_candidate_diff_tolerates_untracked_nested_repository(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    manager = GitWorkspaceManager(tmp_path / "state")
    project = manager.register(repo)
    base = manager.revision(repo)
    workspace = manager.create_task_workspace(project, "run", "task", base)
    nested = workspace / "vendored"
    nested.mkdir()
    git(nested, "init", "-q")
    (workspace / "added.txt").write_text("hello\n")
    diff = manager.candidate_diff(workspace, base)
    assert "+hello" in diff
    assert "new untracked directory (not diffed): vendored/" in diff


def test_cleanup_removes_stray_non_worktree_directories(tmp_path: Path):
    repo = make_repo(tmp_path / "repo")
    manager = GitWorkspaceManager(tmp_path / "state")
    project = manager.register(repo)
    manager.create_task_workspace(project, "run", "real", manager.revision(repo))
    stray = manager.worktree_root / project.id / "run" / "half-created"
    stray.mkdir()
    (stray / "leftover.txt").write_text("x")
    assert manager.remove_run_workspaces(project, "run") == ["half-created", "real"]
    assert not (manager.worktree_root / project.id / "run").exists()
