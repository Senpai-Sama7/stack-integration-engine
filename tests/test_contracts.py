from datetime import datetime

import pytest
from pydantic import ValidationError

from stack_integration.contracts.models import (
    Lease,
    Provider,
    Review,
    TaskStatus,
    Verdict,
    assert_task_transition,
)


def test_unknown_fields_are_rejected():
    with pytest.raises(ValidationError):
        Review(
            id="review",
            project_id="project",
            run_id="run",
            task_id="task",
            reviewer_id="reviewer",
            reviewer_provider=Provider.CLAUDE,
            author_provider=Provider.CODEX,
            candidate_hash="a" * 64,
            verdict=Verdict.APPROVE,
            invented=True,
        )


def test_self_provider_review_is_rejected():
    with pytest.raises(ValidationError, match="opposite provider"):
        Review(
            id="review",
            project_id="project",
            task_id="task",
            reviewer_id="reviewer",
            reviewer_provider=Provider.CODEX,
            author_provider=Provider.CODEX,
            candidate_hash="a" * 64,
            verdict=Verdict.APPROVE,
        )


def test_naive_timestamp_is_rejected():
    with pytest.raises(ValidationError, match="timezone"):
        Review(
            id="review",
            project_id="project",
            task_id="task",
            reviewer_id="reviewer",
            reviewer_provider=Provider.CLAUDE,
            author_provider=Provider.CODEX,
            candidate_hash="a" * 64,
            verdict=Verdict.APPROVE,
            created_at=datetime.now(),
        )


def test_invalid_transition_is_rejected():
    with pytest.raises(ValueError, match="invalid task transition"):
        assert_task_transition(TaskStatus.READY, TaskStatus.VERIFIED)


def test_lease_naive_datetime_is_rejected():
    with pytest.raises(ValidationError, match="timezone"):
        Lease(
            id="lease",
            project_id="project",
            run_id="run",
            task_id="task",
            actor_id="actor",
            attempt=1,
            fencing_token=1,
            expires_at=datetime.now(),
        )
