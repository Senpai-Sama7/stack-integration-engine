"""Shared collaboration state with identity and candidate checks."""

from __future__ import annotations

import json

from stack_integration.contracts.models import (
    Artifact,
    Finding,
    Message,
    Review,
    SideEffect,
    Task,
    Verdict,
    new_id,
    utc_now,
)
from stack_integration.policy import PolicyEngine
from stack_integration.security import redact_text, redact_value
from stack_integration.storage import ArtifactStore, ControllerDatabase


class CoordinationService:
    def __init__(
        self,
        database: ControllerDatabase,
        artifacts: ArtifactStore,
        policy: PolicyEngine,
    ):
        self.database = database
        self.artifacts = artifacts
        self.policy = policy

    def send_message(self, message: Message) -> bool:
        self.policy.require(
            message.sender_id, project_id=message.project_id, action=SideEffect.READ_ONLY
        )
        if not self.database.deduplicate_message(message.id):
            return False
        message.body = redact_text(message.body)
        self.database.put("message", message, actor_id=message.sender_id, event_type="message.sent")
        return True

    def receive_messages(self, actor_id: str, project_id: str) -> list[Message]:
        self.policy.require(actor_id, project_id=project_id, action=SideEffect.READ_ONLY)
        messages = self.database.list("message", Message, project_id=project_id)
        return [item for item in messages if item.recipient_id in {actor_id, "broadcast"}]

    def publish_finding(self, finding: Finding) -> None:
        self.policy.require(
            finding.author_id, project_id=finding.project_id, action=SideEffect.READ_ONLY
        )
        finding.statement = redact_text(finding.statement)
        self.database.put(
            "finding", finding, actor_id=finding.author_id, event_type="finding.published"
        )

    def submit_review(self, review: Review) -> None:
        self.policy.require(
            review.reviewer_id, project_id=review.project_id, action=SideEffect.READ_ONLY
        )
        task = self.database.get("task", review.task_id, Task)
        if review.project_id != task.project_id:
            raise ValueError("review project does not match task project")
        if review.run_id != task.run_id:
            raise ValueError("review run does not match task run")
        if task.candidate_hash != review.candidate_hash:
            raise ValueError("review candidate does not match the task's current candidate")
        if task.owner_provider != review.author_provider:
            raise ValueError("review author provider does not match task ownership")
        self.database.put(
            "review", review, actor_id=review.reviewer_id, event_type="review.submitted"
        )

    def valid_reviews(self, task: Task) -> list[Review]:
        return [
            review
            for review in self.database.list(
                "review", Review, project_id=task.project_id, run_id=task.run_id
            )
            if review.task_id == task.id and review.candidate_hash == task.candidate_hash
        ]

    def approved(self, task: Task) -> bool:
        return any(review.verdict == Verdict.APPROVE for review in self.valid_reviews(task))

    def build_context_packet(self, task: Task, base_revision: str) -> Artifact:
        findings = [
            item
            for item in self.database.list(
                "finding", Finding, project_id=task.project_id, run_id=task.run_id
            )
            if item.task_id in {None, task.id}
        ]
        messages = [
            item
            for item in self.database.list(
                "message", Message, project_id=task.project_id, run_id=task.run_id
            )
            if item.task_id in {None, task.id}
        ]
        packet = redact_value(
            {
                "schema_version": "1.0",
                "task": task.model_dump(mode="json"),
                "base_revision": base_revision,
                "findings": [item.model_dump(mode="json") for item in findings],
                "messages": [item.model_dump(mode="json") for item in messages],
                "generated_at": utc_now().isoformat(),
                "freshness": {"source_revision": base_revision},
            }
        )
        return self.artifacts.register_bytes(
            json.dumps(packet, indent=2, sort_keys=True).encode(),
            project_id=task.project_id,
            run_id=task.run_id,
            task_id=task.id,
            producer_id="controller",
            media_type="application/json",
            base_revision=base_revision,
        )

    def propose_message(
        self,
        *,
        task: Task,
        sender_id: str,
        recipient_id: str,
        purpose: str,
        body: str,
        references: list[str] | None = None,
    ) -> Message:
        return Message(
            id=new_id("msg"),
            project_id=task.project_id,
            run_id=task.run_id,
            task_id=task.id,
            sender_id=sender_id,
            recipient_id=recipient_id,
            purpose=purpose,
            body=body,
            references=references or [],
        )
