import subprocess
from pathlib import Path

import pytest

from stack_integration.config import Settings
from stack_integration.contracts.models import ActorRole, Provider, Review, SideEffect, Verdict
from stack_integration.controller import CollaborationController
from stack_integration.policy import Grant


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


def test_submit_review_requires_matching_task_run(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    controller = CollaborationController(Settings.load(tmp_path / "state"))
    try:
        run = controller.create_run(repo, "review", ["REQ-1"])
        task = controller.add_tasks(
            run.id,
            [{"id": "task-1", "description": "analyze", "provider": "codex"}],
        )[0]
        task.candidate_hash = "abc123"
        controller.database.save_task(task, expected_revision=task.revision)
        controller.policy.register_verified_grant(
            Grant(
                actor_id="reviewer",
                project_id=run.project_id,
                role=ActorRole.REVIEWER,
                actions=frozenset({SideEffect.READ_ONLY}),
                scope_paths=(".",),
                provider=Provider.CLAUDE,
            )
        )
        with pytest.raises(ValueError, match="review run does not match"):
            controller.coordination.submit_review(
                Review(
                    id="review-1",
                    project_id=run.project_id,
                    run_id="other-run",
                    task_id=task.id,
                    reviewer_id="reviewer",
                    reviewer_provider=Provider.CLAUDE,
                    author_provider=Provider.CODEX,
                    candidate_hash="abc123",
                    verdict=Verdict.APPROVE,
                )
            )
    finally:
        controller.close()
