"""Small MCP stdio bridge exposing role-scoped collaboration operations."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import os
import secrets
import sys
from datetime import timedelta
from pathlib import Path
from typing import Any

from stack_integration.config import Settings
from stack_integration.contracts.models import (
    ActorRole,
    Decision,
    Finding,
    Message,
    Project,
    Provider,
    Review,
    Run,
    SideEffect,
    Task,
    Verdict,
    new_id,
    utc_now,
)
from stack_integration.controller.runtime import CollaborationController
from stack_integration.policy import Grant


class BridgeAuthenticationError(PermissionError):
    pass


class BridgeTokenManager:
    def __init__(self, secret_path: str | Path):
        self.secret_path = Path(secret_path).expanduser().resolve()

    def _secret(self, create: bool) -> bytes:
        if self.secret_path.exists():
            return self.secret_path.read_bytes()
        if not create:
            raise BridgeAuthenticationError("bridge secret is not initialized")
        self.secret_path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_bytes(32)
        descriptor = os.open(self.secret_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as target:
            target.write(value)
        return value

    def issue(self, grant: Grant, ttl_seconds: int = 3600) -> str:
        payload = {
            "actor_id": grant.actor_id,
            "project_id": grant.project_id,
            "role": grant.role.value,
            "provider": grant.provider.value if grant.provider else None,
            "actions": sorted(item.value for item in grant.actions),
            "scope_paths": list(grant.scope_paths),
            "expires_at": (utc_now() + timedelta(seconds=ttl_seconds)).isoformat(),
            "nonce": secrets.token_hex(12),
        }
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        signature = hmac.new(self._secret(True), body, hashlib.sha256).digest()
        return (
            base64.urlsafe_b64encode(body).decode()
            + "."
            + base64.urlsafe_b64encode(signature).decode()
        )

    def verify(self, token: str) -> Grant:
        try:
            encoded_body, encoded_signature = token.split(".", 1)
            body = base64.urlsafe_b64decode(encoded_body)
            signature = base64.urlsafe_b64decode(encoded_signature)
            expected = hmac.new(self._secret(False), body, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise BridgeAuthenticationError("invalid bridge token signature")
            payload = json.loads(body)
            expires = __import__("datetime").datetime.fromisoformat(payload["expires_at"])
            if expires <= utc_now():
                raise BridgeAuthenticationError("bridge token expired")
            return Grant(
                actor_id=payload["actor_id"],
                project_id=payload["project_id"],
                role=ActorRole(payload["role"]),
                actions=frozenset(SideEffect(item) for item in payload["actions"]),
                scope_paths=tuple(payload["scope_paths"]),
                provider=Provider(payload["provider"]) if payload.get("provider") else None,
            )
        except BridgeAuthenticationError:
            raise
        except Exception as error:
            raise BridgeAuthenticationError("malformed bridge token") from error


TOOLS = [
    {
        "name": "task_list",
        "description": "List tasks in the authenticated project/run scope",
        "inputSchema": {
            "type": "object",
            "properties": {"run_id": {"type": ["string", "null"]}},
            "additionalProperties": False,
        },
    },
    {
        "name": "task_get",
        "description": "Get one authorized task",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "task_claim",
        "description": "Atomically claim a ready task and receive its fencing token",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "task_heartbeat",
        "description": "Renew a task lease using its fencing token",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "fencing_token": {"type": "integer"},
            },
            "required": ["task_id", "fencing_token"],
            "additionalProperties": False,
        },
    },
    {
        "name": "message_send",
        "description": "Send an evidence-scoped peer message",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": ["string", "null"]},
                "task_id": {"type": ["string", "null"]},
                "recipient_id": {"type": "string"},
                "purpose": {"type": "string"},
                "body": {"type": "string"},
                "references": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["recipient_id", "purpose", "body"],
            "additionalProperties": False,
        },
    },
    {
        "name": "message_receive",
        "description": "Receive messages addressed to this authenticated actor",
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "finding_publish",
        "description": "Publish an evidence-bearing finding",
        "inputSchema": {
            "type": "object",
            "properties": {
                "run_id": {"type": ["string", "null"]},
                "task_id": {"type": ["string", "null"]},
                "kind": {"type": "string"},
                "statement": {"type": "string"},
                "severity": {"type": "string"},
                "evidence_artifact_ids": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["kind", "statement", "severity"],
            "additionalProperties": False,
        },
    },
]

TOOLS.extend(
    [
        {
            "name": "task_propose",
            "description": "Propose and admit a task through controller validation",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "task_id": {"type": "string"},
                    "description": {"type": "string"},
                    "provider": {"type": "string", "enum": ["codex", "claude"]},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "allowed_paths": {"type": "array", "items": {"type": "string"}},
                    "acceptance_ids": {"type": "array", "items": {"type": "string"}},
                    "side_effect": {
                        "type": "string",
                        "enum": ["read_only", "worktree_write"],
                    },
                },
                "required": ["run_id", "task_id", "description", "provider", "side_effect"],
                "additionalProperties": False,
            },
        },
        {
            "name": "artifact_submit",
            "description": "Register a bounded text artifact in authenticated project scope",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": ["string", "null"]},
                    "task_id": {"type": ["string", "null"]},
                    "text": {"type": "string", "maxLength": 1048576},
                    "candidate_revision": {"type": ["string", "null"]},
                },
                "required": ["text"],
                "additionalProperties": False,
            },
        },
        {
            "name": "artifact_get",
            "description": "Read a bounded artifact from the authenticated project",
            "inputSchema": {
                "type": "object",
                "properties": {"artifact_id": {"type": "string"}},
                "required": ["artifact_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "finding_query",
            "description": "Query project findings, optionally narrowed to one run/task",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": ["string", "null"]},
                    "task_id": {"type": ["string", "null"]},
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "review_submit",
            "description": "Submit an opposite-provider review for the current candidate",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "string"},
                    "candidate_hash": {"type": "string"},
                    "verdict": {
                        "type": "string",
                        "enum": ["approve", "request_changes", "abstain"],
                    },
                    "requirement_coverage": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "finding_ids": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["task_id", "candidate_hash", "verdict"],
                "additionalProperties": False,
            },
        },
        {
            "name": "decision_propose",
            "description": "Record alternatives and evidence without granting execution authority",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": ["string", "null"]},
                    "question": {"type": "string"},
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "rationale": {"type": "string"},
                    "evidence_artifact_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["question", "alternatives", "rationale"],
                "additionalProperties": False,
            },
        },
        {
            "name": "run_checkpoint",
            "description": "Persist bounded restart context as an artifact",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "run_id": {"type": "string"},
                    "task_id": {"type": ["string", "null"]},
                    "summary": {"type": "string", "maxLength": 200000},
                },
                "required": ["run_id", "summary"],
                "additionalProperties": False,
            },
        },
    ]
)

TOOLS.append(
    {
        "name": "verification_request",
        "description": "Run one operator-admitted check against the task's current candidate",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "definition_id": {"type": "string"},
            },
            "required": ["task_id", "definition_id"],
            "additionalProperties": False,
        },
    }
)


BRIDGE_TEXT_FIELD_LIMIT = 65536


class CoordinationBridge:
    def __init__(self, controller: CollaborationController, grant: Grant):
        self.controller = controller
        self.grant = grant
        self.controller.policy.register_verified_grant(grant)

    @staticmethod
    def _bounded(value: str, *, field: str, limit: int = BRIDGE_TEXT_FIELD_LIMIT) -> str:
        if len(value.encode()) > limit:
            raise ValueError(f"{field} exceeds {limit}-byte bridge limit")
        return value

    def call(self, name: str, arguments: dict[str, Any]) -> Any:
        if name == "task_list":
            self.controller.policy.require(
                self.grant.actor_id,
                project_id=self.grant.project_id,
                action=SideEffect.READ_ONLY,
            )
            return [
                task.model_dump(mode="json")
                for task in self.controller.database.list(
                    "task",
                    Task,
                    project_id=self.grant.project_id,
                    run_id=arguments.get("run_id"),
                )
            ]
        if name == "task_get":
            task = self.controller.database.get("task", arguments["task_id"], Task)
            self.controller.policy.require(
                self.grant.actor_id,
                project_id=task.project_id,
                action=SideEffect.READ_ONLY,
            )
            return task.model_dump(mode="json")
        if name == "task_claim":
            task = self.controller.database.get("task", arguments["task_id"], Task)
            needed = (
                SideEffect.READ_ONLY
                if task.side_effect == SideEffect.READ_ONLY
                else SideEffect.WORKTREE_WRITE
            )
            self.controller.policy.require(
                self.grant.actor_id, project_id=task.project_id, action=needed
            )
            return self.controller.scheduler.claim(task.id, self.grant.actor_id).model_dump(
                mode="json"
            )
        if name == "task_heartbeat":
            task = self.controller.database.get("task", arguments["task_id"], Task)
            if task.project_id != self.grant.project_id:
                raise PermissionError("cross-project heartbeat denied")
            return self.controller.scheduler.heartbeat(
                arguments["task_id"], self.grant.actor_id, arguments["fencing_token"]
            ).model_dump(mode="json")
        if name == "task_propose":
            if self.grant.role not in {ActorRole.LEAD, ActorRole.BUILDER}:
                raise PermissionError("only a lead or builder may propose tasks")
            run = self.controller.database.get("run", arguments["run_id"], Run)
            if run.project_id != self.grant.project_id:
                raise PermissionError("cross-project task proposal denied")
            side_effect = SideEffect(arguments["side_effect"])
            allowed_paths = list(arguments.get("allowed_paths", []))
            if side_effect != SideEffect.READ_ONLY:
                for path in allowed_paths:
                    self.controller.policy.require(
                        self.grant.actor_id,
                        project_id=run.project_id,
                        action=SideEffect.WORKTREE_WRITE,
                        relative_path=path,
                    )
            task = Task(
                id=arguments["task_id"],
                project_id=run.project_id,
                run_id=run.id,
                description=arguments["description"],
                owner_provider=Provider(arguments["provider"]),
                dependencies=list(arguments.get("dependencies", [])),
                allowed_paths=allowed_paths,
                acceptance_ids=list(arguments.get("acceptance_ids", [])),
                side_effect=side_effect,
            )
            self.controller.scheduler.admit_tasks([task])
            return task.model_dump(mode="json")
        if name == "message_send":
            message = Message(
                id=new_id("msg"),
                project_id=self.grant.project_id,
                run_id=arguments.get("run_id"),
                task_id=arguments.get("task_id"),
                sender_id=self.grant.actor_id,
                recipient_id=arguments["recipient_id"],
                purpose=self._bounded(arguments["purpose"], field="message purpose"),
                body=self._bounded(arguments["body"], field="message body"),
                references=arguments.get("references", []),
            )
            self.controller.coordination.send_message(message)
            return message.model_dump(mode="json")
        if name == "message_receive":
            return [
                message.model_dump(mode="json")
                for message in self.controller.coordination.receive_messages(
                    self.grant.actor_id, self.grant.project_id
                )
            ]
        if name == "finding_publish":
            finding = Finding(
                id=new_id("finding"),
                project_id=self.grant.project_id,
                run_id=arguments.get("run_id"),
                task_id=arguments.get("task_id"),
                author_id=self.grant.actor_id,
                kind=arguments["kind"],
                statement=self._bounded(arguments["statement"], field="finding statement"),
                severity=arguments["severity"],
                evidence_artifact_ids=arguments.get("evidence_artifact_ids", []),
            )
            self.controller.coordination.publish_finding(finding)
            return finding.model_dump(mode="json")
        if name == "finding_query":
            self.controller.policy.require(
                self.grant.actor_id,
                project_id=self.grant.project_id,
                action=SideEffect.READ_ONLY,
            )
            findings = self.controller.database.list(
                "finding",
                Finding,
                project_id=self.grant.project_id,
                run_id=arguments.get("run_id"),
            )
            task_id = arguments.get("task_id")
            return [
                finding.model_dump(mode="json")
                for finding in findings
                if task_id is None or finding.task_id == task_id
            ]
        if name == "artifact_submit":
            self.controller.policy.require(
                self.grant.actor_id,
                project_id=self.grant.project_id,
                action=SideEffect.READ_ONLY,
            )
            text = str(arguments["text"])
            if len(text.encode()) > 1_048_576:
                raise ValueError("artifact exceeds one MiB bridge limit")
            artifact = self.controller.artifacts.register_text(
                text,
                project_id=self.grant.project_id,
                run_id=arguments.get("run_id"),
                task_id=arguments.get("task_id"),
                producer_id=self.grant.actor_id,
                candidate_revision=arguments.get("candidate_revision"),
            )
            return artifact.model_dump(mode="json")
        if name == "artifact_get":
            self.controller.policy.require(
                self.grant.actor_id,
                project_id=self.grant.project_id,
                action=SideEffect.READ_ONLY,
            )
            content = self.controller.artifacts.read(
                arguments["artifact_id"], project_id=self.grant.project_id
            )
            if len(content) > 1_048_576:
                raise ValueError("artifact exceeds one MiB bridge read limit")
            return {"artifact_id": arguments["artifact_id"], "text": content.decode()}
        if name == "review_submit":
            if self.grant.role != ActorRole.REVIEWER:
                raise PermissionError("only a reviewer grant may submit reviews")
            task = self.controller.database.get("task", arguments["task_id"], Task)
            if task.project_id != self.grant.project_id:
                raise PermissionError("cross-project review denied")
            if self.grant.provider is None:
                raise PermissionError("reviewer grant lacks a provider identity")
            review = Review(
                id=new_id("review"),
                project_id=self.grant.project_id,
                run_id=task.run_id,
                task_id=task.id,
                reviewer_id=self.grant.actor_id,
                reviewer_provider=self.grant.provider,
                author_provider=task.owner_provider,
                candidate_hash=arguments["candidate_hash"],
                verdict=Verdict(arguments["verdict"]),
                requirement_coverage=list(arguments.get("requirement_coverage", [])),
                finding_ids=list(arguments.get("finding_ids", [])),
            )
            self.controller.coordination.submit_review(review)
            return review.model_dump(mode="json")
        if name == "decision_propose":
            self.controller.policy.require(
                self.grant.actor_id,
                project_id=self.grant.project_id,
                action=SideEffect.READ_ONLY,
            )
            decision = Decision(
                id=new_id("decision"),
                project_id=self.grant.project_id,
                run_id=arguments.get("run_id"),
                question=self._bounded(arguments["question"], field="decision question"),
                alternatives=list(arguments["alternatives"]),
                rationale=self._bounded(arguments["rationale"], field="decision rationale"),
                evidence_artifact_ids=list(arguments.get("evidence_artifact_ids", [])),
                decider_id=self.grant.actor_id,
            )
            self.controller.database.put(
                "decision",
                decision,
                actor_id=self.grant.actor_id,
                event_type="decision.proposed",
            )
            return decision.model_dump(mode="json")
        if name == "run_checkpoint":
            run = self.controller.database.get("run", arguments["run_id"], Run)
            if run.project_id != self.grant.project_id:
                raise PermissionError("cross-project checkpoint denied")
            self.controller.policy.require(
                self.grant.actor_id,
                project_id=run.project_id,
                action=SideEffect.READ_ONLY,
            )
            artifact = self.controller.artifacts.register_text(
                str(arguments["summary"]),
                project_id=run.project_id,
                run_id=run.id,
                task_id=arguments.get("task_id"),
                producer_id=self.grant.actor_id,
            )
            return artifact.model_dump(mode="json")
        if name == "verification_request":
            if self.grant.role not in {
                ActorRole.VERIFIER,
                ActorRole.CONTROLLER,
                ActorRole.OPERATOR,
            }:
                raise PermissionError("only a verifier grant may request independent checks")
            task = self.controller.database.get("task", arguments["task_id"], Task)
            self.controller.policy.require(
                self.grant.actor_id,
                project_id=task.project_id,
                action=SideEffect.PROCESS,
            )
            if not task.run_id or not task.candidate_hash:
                raise ValueError("task has no current candidate")
            run = self.controller.database.get("run", task.run_id, Run)
            try:
                definition = next(
                    item for item in run.checks if item.id == arguments["definition_id"]
                )
            except StopIteration as error:
                raise ValueError("verification definition is not admitted on this run") from error
            project = self.controller.database.get("project", task.project_id, Project)
            check = asyncio.run(
                self.controller.verifier.run(
                    definition,
                    project_id=task.project_id,
                    run_id=run.id,
                    task_id=task.id,
                    candidate_hash=task.candidate_hash,
                    cwd=task.workspace or project.root,
                )
            )
            return check.model_dump(mode="json")
        raise ValueError(f"unknown bridge tool: {name}")

    def serve_stdio(self) -> None:
        for raw in sys.stdin.buffer:
            request: dict[str, Any] | None = None
            try:
                request = json.loads(raw)
                response = self._handle(request)
                if response is not None:
                    sys.stdout.write(json.dumps(response, separators=(",", ":")) + "\n")
                    sys.stdout.flush()
            except Exception as error:
                request_id = request.get("id") if request else None
                sys.stdout.write(
                    json.dumps(
                        {
                            "jsonrpc": "2.0",
                            "id": request_id,
                            "error": {"code": -32000, "message": str(error)},
                        },
                        separators=(",", ":"),
                    )
                    + "\n"
                )
                sys.stdout.flush()

    def _handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        request_id = request.get("id")
        result: dict[str, Any]
        if request_id is None:
            return None
        if method == "initialize":
            result = {
                "protocolVersion": "2025-06-18",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "stack-agent-bridge", "version": "0.2.0"},
            }
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            params = request.get("params", {})
            value = self.call(params.get("name", ""), params.get("arguments", {}))
            result = {
                "content": [{"type": "text", "text": json.dumps(value, sort_keys=True)}],
                "isError": False,
            }
        elif method == "ping":
            result = {}
        else:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"method not found: {method}"},
            }
        return {"jsonrpc": "2.0", "id": request_id, "result": result}


def bridge_from_environment(state_root: str | Path | None = None) -> CoordinationBridge:
    settings = Settings.load(state_root)
    token = os.environ.get("STACK_AGENT_GRANT")
    if not token:
        raise BridgeAuthenticationError("STACK_AGENT_GRANT is required")
    grant = BridgeTokenManager(settings.state_root / "bridge.key").verify(token)
    return CoordinationBridge(CollaborationController(settings), grant)
