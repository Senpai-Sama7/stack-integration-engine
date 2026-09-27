import subprocess

import pytest

from stack_integration.bridge.server import (
    BridgeAuthenticationError,
    BridgeTokenManager,
    CoordinationBridge,
)
from stack_integration.config import Settings
from stack_integration.contracts.models import ActorRole, Provider, SideEffect
from stack_integration.controller import CollaborationController
from stack_integration.policy import Grant


def test_signed_bridge_grant_round_trip_and_tamper(tmp_path):
    manager = BridgeTokenManager(tmp_path / "bridge.key")
    grant = Grant(
        "codex-worker",
        "p1",
        ActorRole.BUILDER,
        frozenset({SideEffect.READ_ONLY}),
        ("src",),
    )
    token = manager.issue(grant, 60)
    assert manager.verify(token) == grant
    with pytest.raises(BridgeAuthenticationError):
        manager.verify(token[:-2] + "xx")


def test_invalid_bridge_secret_is_rejected_for_verification(tmp_path):
    secret = tmp_path / "bridge.key"
    secret.write_bytes(b"short")
    with pytest.raises(BridgeAuthenticationError, match="invalid length"):
        BridgeTokenManager(secret).verify("e30=.AA==")


def test_bridge_tools_share_authoritative_state(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text("fixture\n")
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
    controller = CollaborationController(Settings.load(tmp_path / "state"))
    try:
        run = controller.create_run(repo, "review", ["REQ"])
        controller.add_tasks(
            run.id,
            [{"id": "task", "description": "inspect", "provider": "codex"}],
        )
        grant = Grant(
            "claude-lead",
            run.project_id,
            ActorRole.LEAD,
            frozenset({SideEffect.READ_ONLY}),
            (".",),
            provider=Provider.CLAUDE,
        )
        bridge = CoordinationBridge(controller, grant)
        assert bridge.call("task_list", {"run_id": run.id})[0]["id"] == "task"
        message = bridge.call(
            "message_send",
            {
                "run_id": run.id,
                "recipient_id": "codex-lead",
                "purpose": "challenge",
                "body": "api_key=do-not-store-this",
            },
        )
        assert "do-not-store-this" not in message["body"]
        finding = bridge.call(
            "finding_publish",
            {
                "run_id": run.id,
                "kind": "observed",
                "statement": "bounded finding",
                "severity": "medium",
            },
        )
        assert bridge.call("finding_query", {"run_id": run.id})[0]["id"] == finding["id"]
        artifact = bridge.call("artifact_submit", {"run_id": run.id, "text": "evidence"})
        assert artifact["content_hash"]
        assert bridge.call("artifact_get", {"artifact_id": artifact["id"]})["text"] == "evidence"
        assert (
            bridge.call(
                "decision_propose",
                {
                    "run_id": run.id,
                    "question": "Which option?",
                    "alternatives": ["A", "B"],
                    "rationale": "proposal only",
                },
            )["decider_id"]
            == "claude-lead"
        )
        assert bridge.call("run_checkpoint", {"run_id": run.id, "summary": "restart here"})[
            "id"
        ].startswith("art_")
    finally:
        controller.close()


def test_task_claim_requires_builder_provider_and_scope(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    (repo / "README.md").write_text("fixture\n")
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
    controller = CollaborationController(Settings.load(tmp_path / "state"))
    try:
        run = controller.create_run(repo, "review", ["REQ"])
        controller.add_tasks(
            run.id,
            [
                {
                    "id": "task",
                    "description": "edit",
                    "provider": "codex",
                    "side_effect": "worktree_write",
                    "allowed_paths": ["src"],
                }
            ],
        )
        reviewer_grant = Grant(
            "claude-reviewer",
            run.project_id,
            ActorRole.REVIEWER,
            frozenset({SideEffect.READ_ONLY}),
            ("src",),
            provider=Provider.CLAUDE,
        )
        with pytest.raises(PermissionError, match="builder"):
            CoordinationBridge(controller, reviewer_grant).call("task_claim", {"task_id": "task"})

        wrong_provider_grant = Grant(
            "claude-builder",
            run.project_id,
            ActorRole.BUILDER,
            frozenset({SideEffect.WORKTREE_WRITE}),
            ("src",),
            provider=Provider.CLAUDE,
        )
        with pytest.raises(PermissionError, match="provider"):
            CoordinationBridge(controller, wrong_provider_grant).call(
                "task_claim", {"task_id": "task"}
            )

        out_of_scope_grant = Grant(
            "codex-builder",
            run.project_id,
            ActorRole.BUILDER,
            frozenset({SideEffect.WORKTREE_WRITE}),
            ("docs",),
            provider=Provider.CODEX,
        )
        with pytest.raises(PermissionError):
            CoordinationBridge(controller, out_of_scope_grant).call(
                "task_claim", {"task_id": "task"}
            )
    finally:
        controller.close()
