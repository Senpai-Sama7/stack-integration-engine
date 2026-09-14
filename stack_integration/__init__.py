"""Stack Integration Engine - Unified AI Governance Orchestrator."""

__version__ = "0.1.0"
__author__ = "Senpai-Sama7"

from stack_integration.core.orchestrator import Orchestrator
from stack_integration.core.types import (
    WorkflowDefinition,
    TaskResult,
    ClaimBundle,
    GateDecision,
)

__all__ = [
    "Orchestrator",
    "WorkflowDefinition",
    "TaskResult",
    "ClaimBundle",
    "GateDecision",
]
