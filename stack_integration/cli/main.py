"""Typer command surface for setup, execution, recovery, and reporting."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Annotated, Any

import typer
from pydantic import BaseModel, ValidationError
from rich.console import Console
from rich.table import Table

from stack_integration import __version__
from stack_integration.bridge import BridgeTokenManager
from stack_integration.config import Settings
from stack_integration.contracts.models import (
    ActorRole,
    Artifact,
    Authorization,
    Budget,
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
from stack_integration.controller.scheduler import AdmissionError
from stack_integration.policy import AuthorizationError, Grant, normalize_scope_path
from stack_integration.storage.database import NotFoundError
from stack_integration.workspaces import GitError

app = typer.Typer(no_args_is_help=True, help="Coordinate local Codex and Claude CLI teams.")
project_app = typer.Typer(help="Register and inspect projects.")
task_app = typer.Typer(help="Operator recovery actions for individual tasks.")
app.add_typer(project_app, name="project")
app.add_typer(task_app, name="task")
console = Console()
error_console = Console(stderr=True)

StateOption = Annotated[Path | None, typer.Option("--state", help="Controller state directory")]

RUN_STATUS_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.PLANNED: {RunStatus.PAUSED, RunStatus.CANCELLED},
    RunStatus.ACTIVE: {RunStatus.PAUSED, RunStatus.CANCELLED},
    RunStatus.PAUSED: {RunStatus.ACTIVE, RunStatus.CANCELLED},
    RunStatus.AWAITING_INPUT: {RunStatus.ACTIVE, RunStatus.PAUSED, RunStatus.CANCELLED},
    RunStatus.BLOCKED: {RunStatus.ACTIVE, RunStatus.PAUSED, RunStatus.CANCELLED},
    RunStatus.CANCELLING: {RunStatus.CANCELLED},
    RunStatus.CANCELLED: set(),
    RunStatus.FAILED: set(),
    RunStatus.COMPLETED: set(),
}

SPEC_KEYS = {"objective", "acceptance", "scope_paths", "tasks", "checks", "budget"}
STATUS_STYLES = {
    "completed": "green",
    "integrated": "green",
    "verified": "green",
    "failed": "red",
    "cancelled": "red",
    "blocked": "yellow",
    "awaiting_input": "yellow",
    "changes_requested": "yellow",
    "paused": "yellow",
}


def _version_callback(value: bool) -> None:
    if value:
        console.print(f"stack-agent {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            envvar="STACK_AGENT_LOG_LEVEL",
            help="Controller log level (DEBUG, INFO, WARNING, ERROR)",
        ),
    ] = "WARNING",
    version: Annotated[
        bool,
        typer.Option(
            "--version", callback=_version_callback, is_eager=True, help="Show the version"
        ),
    ] = False,
) -> None:
    """Coordinate local Codex and Claude CLI teams."""
    level = getattr(logging, log_level.upper(), None)
    if not isinstance(level, int):
        raise typer.BadParameter(f"unknown log level: {log_level}")
    logging.basicConfig(
        level=level, format="%(asctime)s %(levelname)s %(name)s: %(message)s", force=True
    )


def _controller(state: Path | None) -> CollaborationController:
    return CollaborationController(Settings.load(state))


@contextmanager
def _operator_errors() -> Iterator[None]:
    """Report expected operator mistakes as one-line errors instead of tracebacks."""
    try:
        yield
    except NotFoundError as error:
        error_console.print(f"[red]error:[/red] record not found: {error.args[0]}")
        raise typer.Exit(2) from error
    except (
        AdmissionError,
        AuthorizationError,
        GitError,
        ValidationError,
        ValueError,
        FileNotFoundError,
    ) as error:
        error_console.print(f"[red]error:[/red] {error}")
        raise typer.Exit(2) from error


def _dump(value: object) -> None:
    console.print_json(json.dumps(value, default=str))


def _styled(status: str) -> str:
    style = STATUS_STYLES.get(status)
    return f"[{style}]{status}[/{style}]" if style else status


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
    """Register a Git repository (or a subdirectory of one) without modifying it."""
    controller = _controller(state)
    try:
        with _operator_errors():
            _dump(controller.register_project(path).model_dump(mode="json"))
    finally:
        controller.close()


def _load_spec(spec: Path) -> dict[str, Any]:
    try:
        payload = json.loads(spec.read_text())
    except json.JSONDecodeError as error:
        raise ValueError(f"{spec} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("run specification must be a JSON object")
    unknown = sorted(set(payload) - SPEC_KEYS)
    if unknown:
        raise ValueError(f"run specification has unknown fields: {unknown}")
    missing = sorted({"objective", "acceptance", "tasks"} - set(payload))
    if missing:
        raise ValueError(f"run specification is missing required fields: {missing}")
    if not isinstance(payload["tasks"], list) or not payload["tasks"]:
        raise ValueError("run specification must declare at least one task")
    if not isinstance(payload["acceptance"], list) or not payload["acceptance"]:
        raise ValueError("run specification must declare at least one acceptance ID")
    if len(set(payload["acceptance"])) != len(payload["acceptance"]):
        raise ValueError("acceptance IDs must be unique")
    covered = {
        acceptance_id
        for task in payload["tasks"]
        if isinstance(task, dict)
        for acceptance_id in task.get("acceptance_ids", payload["acceptance"])
    }
    uncovered = sorted(set(payload["acceptance"]) - covered)
    if uncovered:
        # The run could never complete: fail at planning time, not after model work.
        raise ValueError(f"no task covers acceptance IDs: {uncovered}")
    return payload


@app.command()
def plan(spec: Path, project: Path, state: StateOption = None) -> None:
    """Validate a JSON run specification and persist its task DAG."""
    controller = _controller(state)
    try:
        with _operator_errors():
            payload = _load_spec(spec)
            run = controller.create_run(
                project,
                payload["objective"],
                list(payload["acceptance"]),
                scope_paths=list(payload.get("scope_paths", ["."])),
                budget=Budget.model_validate(payload["budget"]) if "budget" in payload else None,
                checks=[CheckDefinition.model_validate(item) for item in payload.get("checks", [])],
            )
            try:
                tasks = controller.add_tasks(run.id, list(payload["tasks"]))
            except Exception:
                # Do not leave an un-runnable, task-less run behind.
                orphan = controller.database.get("run", run.id, Run)
                orphan.status = RunStatus.CANCELLED
                controller.database.save_run(orphan, expected_revision=orphan.revision)
                raise
            project_record = controller.database.get("project", run.project_id, Project)
            dirty = controller.workspaces.dirty_paths(project_record.root)
            warnings = (
                [
                    f"{len(dirty)} uncommitted path(s) in the project are not part of base "
                    f"revision {run.base_revision[:12]}; workers will not see them"
                ]
                if dirty
                else []
            )
            _dump(
                {
                    "run": run.model_dump(mode="json"),
                    "tasks": [t.model_dump(mode="json") for t in tasks],
                    "warnings": warnings,
                }
            )
    finally:
        controller.close()


@app.command("run")
def run_command(
    run_id: str,
    summary: Annotated[
        bool, typer.Option("--summary", help="Print only the run and its summary")
    ] = False,
    state: StateOption = None,
) -> None:
    """Execute admitted tasks, cross-review, verify, and integrate."""
    controller = _controller(state)
    try:
        with _operator_errors():
            run = asyncio.run(controller.execute_run(run_id))
            report = controller.run_report(run.id)
            _dump({"run": report["run"], "summary": report["summary"]} if summary else report)
        if run.status != RunStatus.COMPLETED:
            raise typer.Exit(1)
    finally:
        controller.close()


@app.command()
def runs(state: StateOption = None) -> None:
    """List every run with its status and task progress."""
    controller = _controller(state)
    try:
        table = Table(title="Runs")
        table.add_column("Run", no_wrap=True, min_width=36)
        table.add_column("Status")
        table.add_column("Created")
        table.add_column("Tasks")
        table.add_column("Objective", overflow="fold")
        for run in controller.list_runs():
            tasks = controller.database.list("task", Task, project_id=run.project_id, run_id=run.id)
            done = sum(
                task.status in {TaskStatus.VERIFIED, TaskStatus.INTEGRATED} for task in tasks
            )
            table.add_row(
                run.id,
                _styled(run.status.value),
                run.created_at.strftime("%Y-%m-%d %H:%M"),
                f"{done}/{len(tasks)}",
                run.objective,
            )
        console.print(table)
    finally:
        controller.close()


@app.command()
def status(run_id: str, state: StateOption = None) -> None:
    """Show authoritative run and task status."""
    controller = _controller(state)
    try:
        with _operator_errors():
            run = controller.database.get("run", run_id, Run)
            tasks = controller.database.list("task", Task, project_id=run.project_id, run_id=run.id)
            table = Table(title=f"{run.id} — {run.status.value}")
            table.add_column("Task", no_wrap=True)
            table.add_column("Provider")
            table.add_column("Side effect")
            table.add_column("Status")
            table.add_column("Attempt", justify="right")
            for task in tasks:
                table.add_row(
                    task.id,
                    task.owner_provider.value,
                    task.side_effect.value,
                    _styled(task.status.value),
                    str(task.attempt),
                )
            console.print(table)
            if run.integration_ref:
                console.print(
                    f"Integrated result: {run.integration_ref} "
                    f"({(run.integration_commit or '')[:12]})"
                )
    finally:
        controller.close()


@app.command()
def inspect(kind: str, record_id: str, state: StateOption = None) -> None:
    """Inspect a raw versioned controller record."""
    controller = _controller(state)
    try:
        with _operator_errors():
            _dump(json.loads(controller.database.get_raw(kind, record_id)))
    finally:
        controller.close()


def _set_status(run_id: str, target: RunStatus, state: Path | None) -> None:
    controller = _controller(state)
    try:
        run = controller.database.get("run", run_id, Run)
        if target not in RUN_STATUS_TRANSITIONS[run.status]:
            raise typer.BadParameter(
                f"invalid run transition: {run.status.value} -> {target.value}"
            )
        run.status = target
        controller.database.save_run(run, expected_revision=run.revision)
        if target == RunStatus.CANCELLED:
            tasks = controller.database.list("task", Task, project_id=run.project_id, run_id=run.id)
            for task in tasks:
                controller.cancel_task(task.id, reason="run cancelled by operator")
        _dump(controller.database.get("run", run.id, Run).model_dump(mode="json"))
    finally:
        controller.close()


@app.command()
def pause(run_id: str, state: StateOption = None) -> None:
    """Stop new dispatch; in-flight tasks finish at their boundary."""
    with _operator_errors():
        _set_status(run_id, RunStatus.PAUSED, state)


@app.command()
def resume(run_id: str, state: StateOption = None) -> None:
    """Re-activate a paused or blocked run; follow with `run RUN_ID`."""
    with _operator_errors():
        _set_status(run_id, RunStatus.ACTIVE, state)


@app.command()
def cancel(run_id: str, state: StateOption = None) -> None:
    """Cancel a run and its tasks; an active `run` process stops its in-flight work."""
    with _operator_errors():
        _set_status(run_id, RunStatus.CANCELLED, state)


@task_app.command("retry")
def task_retry(task_id: str, state: StateOption = None) -> None:
    """Return an awaiting-input, blocked, reconciling, or changes-requested task to ready.

    Use this only after inspecting the task's worktree and any external side effect
    (docs/RECOVERY.md); then `resume` and `run` the run again.
    """
    controller = _controller(state)
    try:
        with _operator_errors():
            _dump(controller.requeue_task(task_id).model_dump(mode="json"))
    finally:
        controller.close()


@task_app.command("cancel")
def task_cancel(
    task_id: str,
    reason: Annotated[str, typer.Option("--reason")] = "cancelled by operator",
    state: StateOption = None,
) -> None:
    """Cancel one task without cancelling its run."""
    controller = _controller(state)
    try:
        with _operator_errors():
            _dump(controller.cancel_task(task_id, reason=reason).model_dump(mode="json"))
    finally:
        controller.close()


@app.command()
def steer(
    run_id: str,
    instruction: str,
    task: Annotated[
        str | None, typer.Option("--task", help="Target one task instead of the whole run")
    ] = None,
    state: StateOption = None,
) -> None:
    """Record an operator instruction for subsequent task prompts and context packets."""
    controller = _controller(state)
    try:
        with _operator_errors():
            run = controller.database.get("run", run_id, Run)
            if task is not None:
                target = controller.database.get("task", task, Task)
                if target.run_id != run.id:
                    raise ValueError(f"task {task} does not belong to run {run.id}")
            message = Message(
                id=new_id("msg"),
                project_id=run.project_id,
                run_id=run.id,
                task_id=task,
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
        with _operator_errors():
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
def cleanup(run_id: str, state: StateOption = None) -> None:
    """Remove a finished run's worktrees; the stack-agent/<run> branch is kept."""
    controller = _controller(state)
    try:
        with _operator_errors():
            removed = controller.cleanup_run(run_id)
            console.print(f"Removed {len(removed)} worktree(s) for {run_id}")
    finally:
        controller.close()


@app.command()
def backup(destination: Path, state: StateOption = None) -> None:
    """Create a consistent SQLite backup."""
    controller = _controller(state)
    try:
        with _operator_errors():
            console.print(str(controller.database.backup(destination)))
    finally:
        controller.close()


SCHEMA_MODELS: list[type[BaseModel]] = [
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


def render_schema(model: type[BaseModel]) -> str:
    return json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"


@app.command()
def schemas(output: Path) -> None:
    """Generate JSON Schemas for the versioned coordination records."""
    output.mkdir(parents=True, exist_ok=True)
    for model in SCHEMA_MODELS:
        (output / f"{model.__name__.lower()}.schema.json").write_text(render_schema(model))
    console.print(f"Generated {len(SCHEMA_MODELS)} schemas in {output}")


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
    console.print(f"Operator token stored in {settings.state_root / 'operator.token'}")
    if os.environ.get("STACK_AGENT_PRINT_TOKEN") == "1":
        console.print(f"Operator token: {token}")
    uvicorn.run(create_app(settings, token), host=host, port=port)


@app.command("issue-grant")
def issue_grant(
    project_id: str,
    actor_id: str,
    role: ActorRole,
    provider: Provider,
    scope: Annotated[list[str] | None, typer.Option("--scope")] = None,
    ttl: Annotated[int, typer.Option("--ttl", min=60, max=86400)] = 3600,
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
    try:
        scope_paths = tuple(normalize_scope_path(item) for item in scope or ["."])
    except AuthorizationError as error:
        raise typer.BadParameter(str(error)) from error
    grant = Grant(
        actor_id,
        project_id,
        role,
        frozenset(allowed[role]),
        scope_paths,
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
