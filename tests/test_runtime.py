import subprocess
from dataclasses import replace
from pathlib import Path

import pytest

from stack_integration.config import Settings
from stack_integration.contracts.models import (
    Capability,
    CapabilityStatus,
    CheckDefinition,
    Provider,
    ProviderResult,
    RunStatus,
)
from stack_integration.controller import CollaborationController
from stack_integration.providers.base import ProviderAdapter


class FakeAdapter(ProviderAdapter):
    def __init__(self, provider):
        super().__init__("fake")
        self.provider = provider

    async def probe(self):
        return Capability(
            id=f"provider.{self.provider.value}",
            provider=self.provider,
            executable="fake",
            status=CapabilityStatus.SUPPORTED,
        )

    async def execute(self, request):
        if request.role.value == "reviewer":
            structured = {
                "verdict": "approve",
                "summary": "covered",
                "requirement_coverage": ["REQ-1"],
                "findings": [],
            }
        else:
            structured = {
                "summary": "analyzed",
                "changed_paths": [],
                "requirements_addressed": ["REQ-1"],
                "known_limitations": [],
            }
        return ProviderResult(
            provider=self.provider,
            status="completed",
            session_id=f"{self.provider.value}-session",
            output="analysis",
            structured_output=structured,
            exit_code=0,
            duration_ms=1,
        )


class BadStructuredAdapter(FakeAdapter):
    async def execute(self, request):
        return ProviderResult(
            provider=self.provider,
            status="completed",
            session_id=f"{self.provider.value}-session",
            output="analysis",
            structured_output=None,
            exit_code=0,
            duration_ms=1,
        )


def make_repo(path: Path):
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "README.md").write_text("fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
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
        cwd=path,
        check=True,
    )


@pytest.mark.asyncio
async def test_read_only_dual_provider_run_completes(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    settings = Settings.load(tmp_path / "state")
    providers = {
        Provider.CODEX: FakeAdapter(Provider.CODEX),
        Provider.CLAUDE: FakeAdapter(Provider.CLAUDE),
    }
    controller = CollaborationController(settings, providers=providers)
    try:
        run = controller.create_run(repo, "Analyze fixture", ["REQ-1"])
        controller.add_tasks(
            run.id,
            [
                {
                    "id": "task-1",
                    "description": "analyze",
                    "provider": "codex",
                    "acceptance_ids": ["REQ-1"],
                }
            ],
        )
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.COMPLETED
        report = controller.run_report(run.id)
        assert len(report["reviews"]) == 1
        assert {item["provider"] for item in report["sessions"]} == {"codex", "claude"}
    finally:
        controller.close()


class WritingFakeAdapter(ProviderAdapter):
    """Builder writes `<task_id>.txt`; records whether a dependency's file is
    already visible in its workspace before it writes its own."""

    def __init__(self, provider, visibility: dict[str, bool]):
        super().__init__("fake")
        self.provider = provider
        self.visibility = visibility

    async def probe(self):
        return Capability(
            id=f"provider.{self.provider.value}",
            provider=self.provider,
            executable="fake",
            status=CapabilityStatus.SUPPORTED,
        )

    async def execute(self, request):
        if request.role.value == "reviewer":
            structured = {
                "verdict": "approve",
                "summary": "ok",
                "requirement_coverage": ["REQ-1"],
                "findings": [],
            }
            return ProviderResult(
                provider=self.provider,
                status="completed",
                session_id=f"{self.provider.value}-session",
                output="",
                structured_output=structured,
                exit_code=0,
                duration_ms=1,
            )
        if request.task_id == "task-b":
            self.visibility["saw_task_a_file"] = (
                Path(request.project_root) / "task-a.txt"
            ).exists()
        filename = f"{request.task_id}.txt"
        (Path(request.project_root) / filename).write_text(request.task_id)
        structured = {
            "summary": "wrote file",
            "changed_paths": [filename],
            "requirements_addressed": [],
            "known_limitations": [],
        }
        return ProviderResult(
            provider=self.provider,
            status="completed",
            session_id=f"{self.provider.value}-session",
            output="wrote",
            structured_output=structured,
            exit_code=0,
            duration_ms=1,
        )


@pytest.mark.asyncio
async def test_dependent_modifying_task_sees_prerequisite_candidate(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    settings = Settings.load(tmp_path / "state")
    visibility: dict[str, bool] = {}
    providers = {
        Provider.CODEX: WritingFakeAdapter(Provider.CODEX, visibility),
        Provider.CLAUDE: WritingFakeAdapter(Provider.CLAUDE, visibility),
    }
    controller = CollaborationController(settings, providers=providers)
    try:
        run = controller.create_run(
            repo,
            "Build two dependent files",
            ["REQ-1"],
            checks=[CheckDefinition(id="noop", name="noop", command=["true"])],
        )
        controller.add_tasks(
            run.id,
            [
                {
                    "id": "task-a",
                    "description": "write a",
                    "provider": "codex",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["task-a.txt"],
                    "acceptance_ids": ["REQ-1"],
                },
                {
                    "id": "task-b",
                    "description": "write b",
                    "provider": "claude",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["task-b.txt"],
                    "dependencies": ["task-a"],
                },
            ],
        )
        completed = await controller.execute_run(run.id)
        assert completed.status == RunStatus.COMPLETED
        assert visibility.get("saw_task_a_file") is True
    finally:
        controller.close()


def test_create_run_preserves_explicit_empty_scope(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    controller = CollaborationController(Settings.load(tmp_path / "state"))
    try:
        run = controller.create_run(repo, "Analyze fixture", ["REQ-1"], scope_paths=[])
        assert run.scope_paths == []
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_doctor_reports_unsupported_nexus_when_script_missing(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    settings = replace(
        Settings.load(tmp_path / "state"),
        nexus_server_script=tmp_path / "no-such-nexus-server.js",
    )
    controller = CollaborationController(
        settings,
        providers={
            Provider.CODEX: FakeAdapter(Provider.CODEX),
            Provider.CLAUDE: FakeAdapter(Provider.CLAUDE),
        },
    )
    try:
        report = await controller.doctor(repo)
        assert report["tools"]["nexus"]["status"] == "unsupported"
    finally:
        controller.close()


@pytest.mark.asyncio
async def test_completed_worker_without_structured_output_fails_task(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    settings = Settings.load(tmp_path / "state")
    controller = CollaborationController(
        settings,
        providers={
            Provider.CODEX: BadStructuredAdapter(Provider.CODEX),
            Provider.CLAUDE: FakeAdapter(Provider.CLAUDE),
        },
    )
    try:
        run = controller.create_run(repo, "Analyze fixture", ["REQ-1"])
        controller.add_tasks(
            run.id,
            [{"id": "task-1", "description": "analyze", "provider": "codex"}],
        )
        task = await controller.execute_task("task-1")
        assert task.status.value == "failed"
    finally:
        controller.close()
