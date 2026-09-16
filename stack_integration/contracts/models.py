"""Strict, versioned records shared by the controller and provider adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(UTC)


def _require_tz(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ValueError("timestamps must include a timezone")
    return value.astimezone(UTC)


def _require_tz_optional(value: datetime | None) -> datetime | None:
    return None if value is None else _require_tz(value)


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, use_enum_values=False)


class CheckDefinition(StrictModel):
    id: str
    name: str
    command: list[str] = Field(min_length=1)
    required: bool = True
    timeout_seconds: float = Field(default=300, gt=0)
    expects_tests: bool = False
    environment: dict[str, str] = Field(default_factory=dict)


class Provider(StrEnum):
    CODEX = "codex"
    CLAUDE = "claude"


class ActorRole(StrEnum):
    OPERATOR = "operator"
    CONTROLLER = "controller"
    LEAD = "lead"
    BUILDER = "builder"
    REVIEWER = "reviewer"
    VERIFIER = "verifier"
    INTEGRATOR = "integrator"


class SideEffect(StrEnum):
    READ_ONLY = "read_only"
    WORKTREE_WRITE = "worktree_write"
    REPOSITORY_WRITE = "repository_write"
    PROCESS = "process"
    NETWORK = "network"
    PUSH = "push"
    DEPLOY = "deploy"
    DELETE = "delete"
    PRIVILEGE = "privilege"


class RunStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    PAUSED = "paused"
    AWAITING_INPUT = "awaiting_input"
    BLOCKED = "blocked"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    FAILED = "failed"
    COMPLETED = "completed"


class TaskStatus(StrEnum):
    PROPOSED = "proposed"
    READY = "ready"
    LEASED = "leased"
    RUNNING = "running"
    SUBMITTED = "submitted"
    REVIEWING = "reviewing"
    CHANGES_REQUESTED = "changes_requested"
    VERIFIED = "verified"
    INTEGRATED = "integrated"
    RECONCILING = "reconciling"
    AWAITING_INPUT = "awaiting_input"
    BLOCKED = "blocked"
    FAILED = "failed"
    CANCELLED = "cancelled"


class SessionStatus(StrEnum):
    REGISTERED = "registered"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    UNKNOWN = "unknown"


class Verdict(StrEnum):
    APPROVE = "approve"
    REQUEST_CHANGES = "request_changes"
    ABSTAIN = "abstain"


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EvidenceKind(StrEnum):
    OBSERVED = "observed"
    INFERRED = "inferred"
    PROPOSED = "proposed"


class CheckStatus(StrEnum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    SKIPPED = "skipped"
    NO_TESTS = "no_tests"


class CapabilityStatus(StrEnum):
    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    UNTESTED = "untested"
    DEGRADED = "degraded"


class Record(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    project_id: str
    run_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)

    @field_validator("created_at")
    @classmethod
    def timestamp_has_timezone(cls, value: datetime) -> datetime:
        return _require_tz(value)


class Project(StrictModel):
    schema_version: Literal["1.0"] = "1.0"
    id: str
    root: str
    git_common_dir: str
    context_policy: Literal["project_only"] = "project_only"
    revision: int = 1
    created_at: datetime = Field(default_factory=utc_now)


class Budget(StrictModel):
    max_sessions: int = Field(default=6, ge=1)
    max_modifying_tasks: int = Field(default=2, ge=1)
    max_verification_jobs: int = Field(default=2, ge=1)
    wall_time_seconds: int = Field(default=7200, ge=1)
    reported_cost_usd: float | None = Field(default=None, ge=0)


class Run(Record):
    objective: str = Field(min_length=1)
    scope_paths: list[str]
    base_revision: str
    acceptance: list[str] = Field(min_length=1)
    acceptance_version: int = 1
    status: RunStatus = RunStatus.PLANNED
    budget: Budget = Field(default_factory=Budget)
    checks: list[CheckDefinition] = Field(default_factory=list)
    revision: int = 1

    @model_validator(mode="after")
    def unique_check_ids(self) -> Run:
        ids = [item.id for item in self.checks]
        if len(ids) != len(set(ids)):
            raise ValueError("check definition IDs must be unique within a run")
        return self


class Task(Record):
    description: str = Field(min_length=1)
    owner_provider: Provider
    owner_role: ActorRole = ActorRole.BUILDER
    dependencies: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    allowed_paths: list[str] = Field(default_factory=list)
    acceptance_ids: list[str] = Field(default_factory=list)
    side_effect: SideEffect = SideEffect.READ_ONLY
    status: TaskStatus = TaskStatus.PROPOSED
    candidate_hash: str | None = None
    candidate_commit: str | None = None
    workspace: str | None = None
    attempt: int = Field(default=0, ge=0)
    revision: int = 1

    @model_validator(mode="after")
    def no_self_dependency(self) -> Task:
        if self.id in self.dependencies:
            raise ValueError("task cannot depend on itself")
        return self


class Lease(Record):
    task_id: str
    actor_id: str
    attempt: int = Field(ge=1)
    fencing_token: int = Field(ge=1)
    expires_at: datetime
    heartbeat_at: datetime = Field(default_factory=utc_now)
    revoked_at: datetime | None = None

    @field_validator("expires_at", "heartbeat_at")
    @classmethod
    def _validate_required_tz(cls, value: datetime) -> datetime:
        return _require_tz(value)

    @field_validator("revoked_at")
    @classmethod
    def _validate_optional_tz(cls, value: datetime | None) -> datetime | None:
        return _require_tz_optional(value)


class Session(Record):
    provider: Provider
    provider_session_id: str | None = None
    parent_id: str | None = None
    role: ActorRole
    status: SessionStatus = SessionStatus.REGISTERED
    grant_id: str
    process_id: int | None = None


class Capability(StrictModel):
    id: str
    provider: Provider
    executable: str
    version: str | None = None
    status: CapabilityStatus = CapabilityStatus.UNTESTED
    features: dict[str, CapabilityStatus] = Field(default_factory=dict)
    observed_at: datetime = Field(default_factory=utc_now)
    detail: str | None = None

    @field_validator("observed_at")
    @classmethod
    def _validate_tz(cls, value: datetime) -> datetime:
        return _require_tz(value)


class Artifact(Record):
    task_id: str | None = None
    producer_id: str
    content_hash: str
    size: int = Field(ge=0)
    media_type: str
    relative_path: str
    base_revision: str | None = None
    candidate_revision: str | None = None


class Finding(Record):
    task_id: str | None = None
    author_id: str
    kind: EvidenceKind
    statement: str = Field(min_length=1)
    severity: Severity = Severity.INFO
    evidence_artifact_ids: list[str] = Field(default_factory=list)
    verified: bool = False


class Review(Record):
    task_id: str
    reviewer_id: str
    reviewer_provider: Provider
    author_provider: Provider
    candidate_hash: str
    verdict: Verdict
    requirement_coverage: list[str] = Field(default_factory=list)
    finding_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def independent_provider(self) -> Review:
        if self.reviewer_provider == self.author_provider:
            raise ValueError("review must come from the opposite provider")
        return self


class Check(Record):
    task_id: str | None = None
    definition_id: str
    candidate_hash: str
    status: CheckStatus
    command: list[str]
    exit_code: int | None = None
    duration_ms: float = Field(ge=0)
    output_artifact_id: str | None = None
    tests_collected: int | None = Field(default=None, ge=0)


class Authorization(Record):
    actor_id: str
    actions: list[SideEffect]
    scope_paths: list[str]
    candidate_hash: str | None = None
    scope_version: int = Field(ge=1)
    expires_at: datetime
    granted_by: str

    @field_validator("expires_at")
    @classmethod
    def _validate_tz(cls, value: datetime) -> datetime:
        return _require_tz(value)


class Decision(Record):
    question: str
    alternatives: list[str]
    evidence_artifact_ids: list[str] = Field(default_factory=list)
    rationale: str
    decider_id: str
    supersedes_id: str | None = None


class Event(Record):
    aggregate_type: str
    aggregate_id: str
    aggregate_revision: int = Field(ge=1)
    causation_id: str | None = None
    actor_id: str
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class Message(Record):
    task_id: str | None = None
    sender_id: str
    recipient_id: str
    purpose: Literal[
        "question",
        "answer",
        "finding",
        "review_request",
        "challenge",
        "decision_proposal",
        "status",
    ]
    body: str
    causation_id: str | None = None
    references: list[str] = Field(default_factory=list)
    acknowledged_at: datetime | None = None

    @field_validator("acknowledged_at")
    @classmethod
    def _validate_tz(cls, value: datetime | None) -> datetime | None:
        return _require_tz_optional(value)


class Usage(Record):
    task_id: str | None = None
    session_id: str
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    reported_cost_usd: float | None = Field(default=None, ge=0)
    estimated: bool = False
    source: str


class ProviderRequest(StrictModel):
    task_id: str
    project_root: str
    prompt: str = Field(min_length=1)
    role: ActorRole
    allowed_paths: list[str] = Field(default_factory=list)
    read_only: bool = True
    session_id: str | None = None
    timeout_seconds: float = Field(default=1200, gt=0)
    output_schema: dict[str, Any] | None = None
    mcp_server_command: list[str] | None = None
    environment: dict[str, str] = Field(default_factory=dict)


class ProviderResult(StrictModel):
    provider: Provider
    status: Literal["completed", "failed", "timeout", "cancelled", "protocol_error"]
    session_id: str | None = None
    output: str = ""
    structured_output: dict[str, Any] | None = None
    error: str | None = None
    exit_code: int | None = None
    duration_ms: float = Field(ge=0)
    usage: dict[str, Any] = Field(default_factory=dict)


TERMINAL_TASK_STATES = {TaskStatus.INTEGRATED, TaskStatus.FAILED, TaskStatus.CANCELLED}

ALLOWED_TASK_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.PROPOSED: {TaskStatus.READY, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.READY: {TaskStatus.LEASED, TaskStatus.BLOCKED, TaskStatus.CANCELLED},
    TaskStatus.LEASED: {TaskStatus.RUNNING, TaskStatus.RECONCILING, TaskStatus.CANCELLED},
    TaskStatus.RUNNING: {
        TaskStatus.SUBMITTED,
        TaskStatus.FAILED,
        TaskStatus.RECONCILING,
        TaskStatus.CANCELLED,
    },
    TaskStatus.SUBMITTED: {TaskStatus.REVIEWING, TaskStatus.CHANGES_REQUESTED},
    TaskStatus.REVIEWING: {
        TaskStatus.CHANGES_REQUESTED,
        TaskStatus.VERIFIED,
        TaskStatus.AWAITING_INPUT,
    },
    TaskStatus.CHANGES_REQUESTED: {TaskStatus.READY, TaskStatus.CANCELLED},
    TaskStatus.VERIFIED: {TaskStatus.INTEGRATED, TaskStatus.BLOCKED},
    TaskStatus.RECONCILING: {
        TaskStatus.READY,
        TaskStatus.AWAITING_INPUT,
        TaskStatus.FAILED,
    },
    TaskStatus.BLOCKED: {TaskStatus.READY, TaskStatus.CANCELLED},
    TaskStatus.AWAITING_INPUT: {TaskStatus.READY, TaskStatus.CANCELLED},
    TaskStatus.FAILED: set(),
    TaskStatus.CANCELLED: set(),
    TaskStatus.INTEGRATED: set(),
}


def assert_task_transition(current: TaskStatus, target: TaskStatus) -> None:
    if target not in ALLOWED_TASK_TRANSITIONS[current]:
        raise ValueError(f"invalid task transition: {current.value} -> {target.value}")
