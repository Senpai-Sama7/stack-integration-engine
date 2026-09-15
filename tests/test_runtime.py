import subprocess
from pathlib import Path

import pytest

from stack_integration.config import Settings
from stack_integration.contracts.models import (
    Capability,
    CapabilityStatus,
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
