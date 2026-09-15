"""Typer command surface for setup, execution, recovery, and reporting."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Annotated

import typer
from pydantic import BaseModel
from rich.console import Console
from rich.table import Table

from stack_integration.bridge import BridgeTokenManager
from stack_integration.config import Settings
from stack_integration.contracts.models import (
    ActorRole,
    Artifact,
    Authorization,
    Capability,
    Check,
    CheckDefinition,
    Decision,
    Event,
    Finding,
    Lease,
    Message,
    Project,
    Provider,
    Review,
    Run,
    RunStatus,
    Session,
    SideEffect,
    Task,
    TaskStatus,
    Usage,
    new_id,
)
from stack_integration.controller import CollaborationController
from stack_integration.policy import Grant

app = typer.Typer(no_args_is_help=True, help="Coordinate local Codex and Claude CLI teams.")
project_app = typer.Typer(help="Register and inspect projects.")
app.add_typer(project_app, name="project")
console = Console()

StateOption = Annotated[Path | None, typer.Option("--state", help="Controller state directory")]


def _controller(state: Path | None) -> CollaborationController:
    return CollaborationController(Settings.load(state))


def _dump(value: object) -> None:
    console.print_json(json.dumps(value, default=str))


@app.command()
def doctor(
    project: Annotated[Path | None, typer.Option("--project")] = None,
    state: StateOption = None,
) -> None:
    """Probe installed providers and optional local intelligence tools."""
    controller = _controller(state)
    try:
        _dump(asyncio.run(controller.doctor(project)))
    finally:
        controller.close()


@project_app.command("add")
def project_add(path: Path, state: StateOption = None) -> None:
    """Register a Git project without modifying its working tree."""
    controller = _controller(state)
    try:
        _dump(controller.register_project(path).model_dump(mode="json"))
    finally:
        controller.close()


@app.command()
def plan(spec: Path, project: Path, state: StateOption = None) -> None:
    """Validate a JSON run specification and persist its task DAG."""
    payload = json.loads(spec.read_text())
    controller = _controller(state)
    try:
        run = controller.create_run(
            project,
            payload["objective"],
            list(payload["acceptance"]),
            scope_paths=list(payload.get("scope_paths", ["."])),
            checks=[CheckDefinition.model_validate(item) for item in payload.get("checks", [])],
        )
        tasks = controller.add_tasks(run.id, list(payload["tasks"]))
        _dump(
            {
                "run": run.model_dump(mode="json"),
                "tasks": [t.model_dump(mode="json") for t in tasks],
            }
        )
    finally:
        controller.close()


@app.command("run")
def run_command(run_id: str, state: StateOption = None) -> None:
    """Execute admitted tasks, cross-review, verify, and integrate."""
    controller = _controller(state)
    try:
        run = asyncio.run(controller.execute_run(run_id))
        _dump(controller.run_report(run.id))
        if run.status != RunStatus.COMPLETED:
            raise typer.Exit(1)
    finally:
        controller.close()


@app.command()
def status(run_id: str, state: StateOption = None) -> None:
    """Show authoritative run and task status."""
    controller = _controller(state)
    try:
        run = controller.database.get("run", run_id, Run)
        tasks = controller.database.list("task", Task, project_id=run.project_id, run_id=run.id)
        table = Table(title=f"{run.id} — {run.status.value}")
        table.add_column("Task")
        table.add_column("Provider")
        table.add_column("Status")
        table.add_column("Attempt", justify="right")
        for task in tasks:
            table.add_row(task.id, task.owner_provider.value, task.status.value, str(task.attempt))
        console.print(table)
    finally:
        controller.close()


@app.command()
def inspect(kind: str, record_id: str, state: StateOption = None) -> None:
    """Inspect a raw versioned controller record."""
    controller = _controller(state)
    try:
        row = controller.database._connection.execute(
            "SELECT body FROM records WHERE kind=? AND id=?", (kind, record_id)
        ).fetchone()
        if row is None:
            raise typer.BadParameter(f"record not found: {kind}/{record_id}")
        _dump(json.loads(row["body"]))
    finally:
        controller.close()


def _set_status(run_id: str, target: RunStatus, state: Path | None) -> None:
    controller = _controller(state)
    try:
        run = controller.database.get("run", run_id, Run)
        run.status = target
        controller.database.save_run(run, expected_revision=run.revision)
        if target == RunStatus.CANCELLED:
            tasks = controller.database.list("task", Task, project_id=run.project_id, run_id=run.id)
            for task in tasks:
                controller.scheduler.force_terminal(
                    task.id,
                    TaskStatus.CANCELLED,
                    actor_id="local-operator",
                    reason="run cancelled by operator",
                )
        _dump(controller.database.get("run", run.id, Run).model_dump(mode="json"))
    finally:
        controller.close()


@app.command()
def pause(run_id: str, state: StateOption = None) -> None:
    """Stop new dispatch; active subprocesses checkpoint at their boundary."""
    _set_status(run_id, RunStatus.PAUSED, state)


@app.command()
def resume(run_id: str, state: StateOption = None) -> None:
    """Resume a paused or blocked run after rechecking prerequisites."""
    _set_status(run_id, RunStatus.ACTIVE, state)


@app.command()
def cancel(run_id: str, state: StateOption = None) -> None:
    """Mark a run cancelled; no new work will be dispatched."""
    _set_status(run_id, RunStatus.CANCELLED, state)


@app.command()
def steer(run_id: str, instruction: str, state: StateOption = None) -> None:
    """Record an operator instruction for all subsequent task context packets."""
    controller = _controller(state)
    try:
        run = controller.database.get("run", run_id, Run)
        message = Message(
            id=new_id("msg"),
            project_id=run.project_id,
            run_id=run.id,
            sender_id="local-operator",
            recipient_id="broadcast",
            purpose="status",
            body=instruction,
        )
        controller.database.put(
            "message", message, actor_id="local-operator", event_type="run.steered"
        )
        _dump(message.model_dump(mode="json"))
    finally:
        controller.close()


@app.command()
def report(
    run_id: str,
    output: Annotated[Path | None, typer.Option("--output")] = None,
    state: StateOption = None,
) -> None:
    """Export the run, evidence, reviews, checks, sessions, and limitations."""
    controller = _controller(state)
    try:
        value = controller.run_report(run_id)
        rendered = json.dumps(value, indent=2, sort_keys=True, default=str) + "\n"
        if output:
            output.write_text(rendered)
            console.print(str(output))
        else:
            console.print_json(rendered)
    finally:
        controller.close()


@app.command()
def backup(destination: Path, state: StateOption = None) -> None:
    """Create a consistent SQLite backup."""
    controller = _controller(state)
    try:
        console.print(str(controller.database.backup(destination)))
    finally:
        controller.close()


@app.command()
def schemas(output: Path) -> None:
    """Generate JSON Schemas for the versioned coordination records."""
    output.mkdir(parents=True, exist_ok=True)
    models: list[type[BaseModel]] = [
        Project,
        Run,
        Task,
        Lease,
        Session,
        Capability,
        Artifact,
        Finding,
        Review,
        Check,
        Decision,
        Authorization,
        Event,
        Message,
        Usage,
    ]
    for model in models:
        target = output / f"{model.__name__.lower()}.schema.json"
        target.write_text(json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n")
    console.print(f"Generated {len(models)} schemas in {output}")


@app.command()
def serve(
    state: StateOption = None,
    host: Annotated[str, typer.Option("--host")] = "127.0.0.1",
    port: Annotated[int, typer.Option("--port")] = 8765,
) -> None:
    """Serve the authenticated status API/dashboard on loopback."""
    if host not in {"127.0.0.1", "::1", "localhost"}:
        raise typer.BadParameter("remote listeners are disabled by local policy")
    try:
        import uvicorn
    except ImportError as error:
        raise typer.BadParameter("install the api extra: pip install '.[api]'") from error
    from stack_integration.api import create_app
    from stack_integration.api.main import ensure_operator_token

    settings = Settings.load(state)
    token = ensure_operator_token(settings)
    console.print(f"Operator token: {token}")
    uvicorn.run(create_app(settings, token), host=host, port=port)


@app.command("issue-grant")
def issue_grant(
    project_id: str,
    actor_id: str,
    role: ActorRole,
    provider: Provider,
    scope: Annotated[list[str] | None, typer.Option("--scope")] = None,
    ttl: Annotated[int, typer.Option("--ttl")] = 3600,
    state: StateOption = None,
) -> None:
    """Issue a short-lived signed token for a local bridge process."""
    settings = Settings.load(state)
    allowed = {
        ActorRole.LEAD: {SideEffect.READ_ONLY},
        ActorRole.BUILDER: {SideEffect.READ_ONLY, SideEffect.WORKTREE_WRITE, SideEffect.PROCESS},
        ActorRole.REVIEWER: {SideEffect.READ_ONLY, SideEffect.PROCESS},
        ActorRole.VERIFIER: {SideEffect.READ_ONLY, SideEffect.PROCESS},
    }
    if role not in allowed:
        raise typer.BadParameter(
            "bridge grants are limited to lead, builder, reviewer, or verifier"
        )
    grant = Grant(
        actor_id,
        project_id,
        role,
        frozenset(allowed[role]),
        tuple(scope or ["."]),
        provider=provider,
    )
    console.print(BridgeTokenManager(settings.state_root / "bridge.key").issue(grant, ttl))


@app.command(hidden=True)
def bridge(state: StateOption = None) -> None:
    """Run the authenticated MCP stdio coordination bridge."""
    from stack_integration.bridge.server import bridge_from_environment

    server = bridge_from_environment(state)
    try:
        server.serve_stdio()
    finally:
        server.controller.close()
