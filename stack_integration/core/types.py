"""Shared types for integration."""

from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class RiskTier(str, Enum):
    READ_ONLY = "read_only"
    WRITE = "write"
    DEPLOY = "deploy"
    PRIVILEGE = "privilege"
    DELETE = "delete"


class GateDecision(str, Enum):
    APPROVE = "approve"
    DEFER = "defer"
    REFUSE = "refuse"
    ESCALATE = "escalate"


class EvidencePointer(BaseModel):
    source: str
    source_confidence: float = Field(ge=0.0, le=1.0)
    evidence_hash: str = ""
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Uncertainty(BaseModel):
    method: str
    value: float = Field(ge=0.0, le=1.0)
    interpretation: str
    gate_recommendation: GateDecision


class Claim(BaseModel):
    statement: str
    claim_type: str
    evidence_pointers: List[EvidencePointer] = Field(default_factory=list)
    uncertainty: Optional[Uncertainty] = None
    risk_tier: RiskTier = RiskTier.READ_ONLY
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ClaimBundle(BaseModel):
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    origin_agent: str
    claims: List[Claim] = Field(default_factory=list)
    decision: GateDecision = GateDecision.DEFER
    reason: str = ""
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None


class TaskResult(BaseModel):
    task_id: str
    status: TaskStatus
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    claims: Optional[ClaimBundle] = None
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WorkflowDefinition(BaseModel):
    id: str
    name: str
    description: str
    steps: List[Dict[str, Any]]
    version: str = "1.0"
    metadata: Dict[str, Any] = Field(default_factory=dict)
