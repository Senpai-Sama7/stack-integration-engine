"""Shared Pydantic models for integration."""

from enum import Enum
from datetime import datetime
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class RiskTier(str, Enum):
    """Risk classification for decisions."""
    READ_ONLY = "read_only"
    WRITE = "write"
    DEPLOY = "deploy"
    PRIVILEGE = "privilege"
    DELETE = "delete"


class GateDecision(str, Enum):
    """Gate evaluation outcome."""
    APPROVE = "approve"
    DEFER = "defer"
    REFUSE = "refuse"
    ESCALATE = "escalate"


class EvidencePointer(BaseModel):
    """Pointer to evidence source."""
    source: str = Field(..., description="Evidence source URL or reference")
    source_confidence: float = Field(..., ge=0.0, le=1.0)
    evidence_hash: str = Field(default="", description="Optional content hash")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class Uncertainty(BaseModel):
    """Uncertainty quantification for claims."""
    method: str = Field(..., description="Method used (semantic_entropy, model_disagreement, etc)")
    value: float = Field(..., ge=0.0, le=1.0, description="Uncertainty score")
    interpretation: str = Field(..., description="Human-readable interpretation")
    gate_recommendation: GateDecision = Field(..., description="Recommended action")


class Claim(BaseModel):
    """Individual claim with evidence and uncertainty."""
    statement: str = Field(..., description="The claim being made")
    claim_type: str = Field(..., description="FACT, INFERENCE, DECISION")
    evidence_pointers: List[EvidencePointer] = Field(default_factory=list)
    uncertainty: Optional[Uncertainty] = None
    risk_tier: RiskTier = Field(default=RiskTier.READ_ONLY)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ClaimBundle(BaseModel):
    """Wrapped result with claims, evidence, and gating."""
    id: str = Field(default_factory=lambda: __import__("uuid").uuid4().hex)
    origin_agent: str = Field(..., description="Agent that created this bundle")
    claims: List[Claim] = Field(default_factory=list)
    decision: GateDecision = Field(default=GateDecision.DEFER)
    reason: str = Field(default="")
    audit_trail: List[Dict[str, Any]] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None

    def approve(self, reason: str = "") -> None:
        """Mark bundle as approved."""
        self.decision = GateDecision.APPROVE
        self.reason = reason
        self.audit_trail.append({
            "action": "approve",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason
        })

    def defer(self, reason: str = "") -> None:
        """Defer bundle for human review."""
        self.decision = GateDecision.DEFER
        self.reason = reason
        self.audit_trail.append({
            "action": "defer",
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason
        })


class TaskResult(BaseModel):
    """Result of a task execution."""
    task_id: str
    status: TaskStatus
    output: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    claims: Optional[ClaimBundle] = None
    duration_ms: float = 0.0
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class WorkflowDefinition(BaseModel):
    """Workflow specification."""
    id: str
    name: str
    description: str
    steps: List[Dict[str, Any]]
    version: str = "1.0"
    metadata: Dict[str, Any] = Field(default_factory=dict)
