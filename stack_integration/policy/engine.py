"""Least-privilege grants enforced at controller endpoints."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from stack_integration.contracts.models import ActorRole, Provider, SideEffect


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True)
class Grant:
    actor_id: str
    project_id: str
    role: ActorRole
    actions: frozenset[SideEffect]
    scope_paths: tuple[str, ...] = ()
    may_modify_policy: bool = False
    provider: Provider | None = None


@dataclass(frozen=True)
class Policy:
    max_sessions: int = 6
    max_modifying_tasks: int = 2
    max_verification_jobs: int = 2
    lease_seconds: int = 90
    heartbeat_seconds: int = 15
    task_wall_time_seconds: int = 1200
    opposite_provider_review: bool = True
    require_nonzero_test_collection: bool = True
    cross_project_reads: bool = False
    remote_listener: bool = False
    single_integration_writer: bool = True
    denied_without_operator: frozenset[SideEffect] = field(
        default_factory=lambda: frozenset(
            {SideEffect.PUSH, SideEffect.DEPLOY, SideEffect.DELETE, SideEffect.PRIVILEGE}
        )
    )

    @classmethod
    def from_file(cls, path: str | Path) -> Policy:
        raw = json.loads(Path(path).read_text())
        return cls(
            max_sessions=raw.get("teams", {}).get("max_concurrent_model_sessions", 6),
            max_modifying_tasks=raw.get("teams", {}).get("max_active_modifying_tasks", 2),
            max_verification_jobs=raw.get("teams", {}).get("max_parallel_verification_jobs", 2),
            lease_seconds=raw.get("scheduling", {}).get("lease_seconds", 90),
            heartbeat_seconds=raw.get("scheduling", {}).get("heartbeat_seconds", 15),
            task_wall_time_seconds=raw.get("scheduling", {}).get("task_wall_time_seconds", 1200),
            opposite_provider_review=raw.get("review", {}).get("opposite_provider_required", True),
            require_nonzero_test_collection=raw.get("review", {}).get(
                "required_test_collection_must_be_nonzero", True
            ),
            cross_project_reads=raw.get("storage", {}).get("cross_project_reads_default", "deny")
            != "deny",
            remote_listener=raw.get("scope", {}).get("remote_listener_enabled", False),
            single_integration_writer=raw.get("scheduling", {}).get(
                "single_integration_writer", True
            ),
        )


ROLE_ACTIONS: dict[ActorRole, frozenset[SideEffect]] = {
    ActorRole.OPERATOR: frozenset(SideEffect),
    ActorRole.CONTROLLER: frozenset(
        {SideEffect.READ_ONLY, SideEffect.WORKTREE_WRITE, SideEffect.PROCESS}
    ),
    ActorRole.LEAD: frozenset({SideEffect.READ_ONLY}),
    ActorRole.BUILDER: frozenset(
        {SideEffect.READ_ONLY, SideEffect.WORKTREE_WRITE, SideEffect.PROCESS}
    ),
    ActorRole.REVIEWER: frozenset({SideEffect.READ_ONLY, SideEffect.PROCESS}),
    ActorRole.VERIFIER: frozenset({SideEffect.READ_ONLY, SideEffect.PROCESS}),
    ActorRole.INTEGRATOR: frozenset(
        {
            SideEffect.READ_ONLY,
            SideEffect.WORKTREE_WRITE,
            SideEffect.REPOSITORY_WRITE,
            SideEffect.PROCESS,
        }
    ),
}


class PolicyEngine:
    def __init__(self, policy: Policy | None = None):
        self.policy = policy or Policy()
        self._grants: dict[str, Grant] = {}

    def register_verified_grant(self, grant: Grant) -> None:
        """Install a grant after an authenticated bridge token has been verified."""
        self._grants[grant.actor_id] = grant

    def issue_grant(
        self,
        *,
        issuer: Grant,
        actor_id: str,
        project_id: str,
        role: ActorRole,
        scope_paths: list[str],
        requested_actions: set[SideEffect] | None = None,
        provider: Provider | None = None,
    ) -> Grant:
        if issuer.role not in {ActorRole.OPERATOR, ActorRole.CONTROLLER}:
            raise AuthorizationError("only the operator or controller may issue grants")
        if issuer.project_id != project_id:
            raise AuthorizationError("grant issuer is outside project scope")
        actions = requested_actions or set(ROLE_ACTIONS[role])
        allowed = set(ROLE_ACTIONS[role])
        if not actions <= allowed:
            raise AuthorizationError("requested actions exceed role authority")
        if actions & self.policy.denied_without_operator and issuer.role != ActorRole.OPERATOR:
            raise AuthorizationError("high-risk authority requires the operator")
        normalized = tuple(sorted({self._normalize_relative(item) for item in scope_paths}))
        grant = Grant(
            actor_id,
            project_id,
            role,
            frozenset(actions),
            normalized,
            provider=provider,
        )
        self._grants[actor_id] = grant
        return grant

    def require(
        self,
        actor_id: str,
        *,
        project_id: str,
        action: SideEffect,
        relative_path: str | None = None,
    ) -> Grant:
        try:
            grant = self._grants[actor_id]
        except KeyError as error:
            raise AuthorizationError(f"no grant for actor {actor_id}") from error
        if grant.project_id != project_id:
            raise AuthorizationError("cross-project access denied")
        if action not in grant.actions:
            raise AuthorizationError(f"{grant.role.value} cannot perform {action.value}")
        if relative_path is not None:
            if not grant.scope_paths:
                raise AuthorizationError("grant has no path scope")
            target = self._normalize_relative(relative_path)
            if not any(
                root == "." or target == root or target.startswith(root + "/")
                for root in grant.scope_paths
            ):
                raise AuthorizationError(f"path outside grant scope: {relative_path}")
        return grant

    @staticmethod
    def _normalize_relative(path: str) -> str:
        candidate = Path(path)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise AuthorizationError("scope paths must be normalized project-relative paths")
        normalized = candidate.as_posix().strip("/")
        return normalized or "."
