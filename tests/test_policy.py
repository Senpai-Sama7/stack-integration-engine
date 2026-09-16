import pytest

from stack_integration.contracts.models import ActorRole, SideEffect
from stack_integration.policy import AuthorizationError, Grant, PolicyEngine


def operator(project="p1"):
    return Grant(
        "operator",
        project,
        ActorRole.OPERATOR,
        frozenset(SideEffect),
        (".",),
        True,
    )


def test_worker_cannot_self_escalate_or_leave_scope():
    policy = PolicyEngine()
    worker = policy.issue_grant(
        issuer=operator(),
        actor_id="worker",
        project_id="p1",
        role=ActorRole.BUILDER,
        scope_paths=["src"],
        requested_actions={SideEffect.READ_ONLY, SideEffect.WORKTREE_WRITE},
    )
    assert worker.role == ActorRole.BUILDER
    with pytest.raises(AuthorizationError):
        policy.issue_grant(
            issuer=worker,
            actor_id="worker",
            project_id="p1",
            role=ActorRole.INTEGRATOR,
            scope_paths=["."],
        )
    with pytest.raises(AuthorizationError):
        policy.require(
            "worker",
            project_id="p1",
            action=SideEffect.WORKTREE_WRITE,
            relative_path="tests/test_escape.py",
        )


def test_dot_scope_allows_any_project_relative_path():
    policy = PolicyEngine()
    policy.issue_grant(
        issuer=operator(),
        actor_id="worker",
        project_id="p1",
        role=ActorRole.BUILDER,
        scope_paths=["."],
        requested_actions={SideEffect.WORKTREE_WRITE},
    )
    policy.require(
        "worker",
        project_id="p1",
        action=SideEffect.WORKTREE_WRITE,
        relative_path="src/file.py",
    )


def test_empty_scope_denies_paths():
    policy = PolicyEngine()
    policy.issue_grant(
        issuer=operator(),
        actor_id="worker",
        project_id="p1",
        role=ActorRole.BUILDER,
        scope_paths=[],
        requested_actions={SideEffect.WORKTREE_WRITE},
    )
    with pytest.raises(AuthorizationError, match="no path scope"):
        policy.require(
            "worker",
            project_id="p1",
            action=SideEffect.WORKTREE_WRITE,
            relative_path="src/file.py",
        )


def test_peer_cannot_gain_push_authority():
    policy = PolicyEngine()
    with pytest.raises(AuthorizationError):
        policy.issue_grant(
            issuer=operator(),
            actor_id="worker",
            project_id="p1",
            role=ActorRole.BUILDER,
            scope_paths=["."],
            requested_actions={SideEffect.PUSH},
        )


def test_explicit_empty_requested_actions_remain_empty():
    policy = PolicyEngine()
    grant = policy.issue_grant(
        issuer=operator(),
        actor_id="empty-actions",
        project_id="p1",
        role=ActorRole.BUILDER,
        scope_paths=["src"],
        requested_actions=set(),
    )
    assert grant.actions == frozenset()


def test_empty_scope_entry_is_rejected():
    policy = PolicyEngine()
    with pytest.raises(AuthorizationError, match="non-empty"):
        policy.issue_grant(
            issuer=operator(),
            actor_id="worker",
            project_id="p1",
            role=ActorRole.BUILDER,
            scope_paths=[""],
            requested_actions={SideEffect.READ_ONLY},
        )
