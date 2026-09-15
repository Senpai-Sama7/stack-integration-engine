"""Shared types for integration."""

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(UTC)


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class RiskTier(StrEnum):
    READ_ONLY = "read_only"
    WRITE = "write"
    DEPLOY = "deploy"
    PRIVILEGE = "privilege"
    DELETE = "delete"


class GateDecision(StrEnum):
    APPROVE = "approve"
    DEFER = "defer"
    REFUSE = "refuse"
    ESCALATE = "escalate"


class EvidencePointer(BaseModel):
    source: str
    source_confidence: float = Field(ge=0.0, le=1.0)
    evidence_hash: str = ""
    timestamp: datetime = Field(default_factory=utc_now)


class Uncertainty(BaseModel):
    method: str
    value: float = Field(ge=0.0, le=1.0)
    interpretation: str
    gate_recommendation: GateDecision


class Claim(BaseModel):
    statement: str
    claim_type: str
    evidence_pointers: list[EvidencePointer] = Field(default_factory=list)
    uncertainty: Uncertainty | None = None
    risk_tier: RiskTier = RiskTier.READ_ONLY
    timestamp: datetime = Field(default_factory=utc_now)


class ClaimBundle(BaseModel):
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    origin_agent: str
    claims: list[Claim] = Field(default_factory=list)
    decision: GateDecision = GateDecision.DEFER
    reason: str = ""
    audit_trail: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    output: dict[str, Any] | None = None
    error: str | None = None
    claims: ClaimBundle | None = None
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=utc_now)


class WorkflowDefinition(BaseModel):
    id: str
    name: str
    description: str
    steps: list[dict[str, Any]]
    version: str = "1.0"
    metadata: dict[str, Any] = Field(default_factory=dict)
