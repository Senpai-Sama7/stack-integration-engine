import subprocess
from pathlib import Path

import pytest
import typer

from stack_integration.cli.main import _set_status
from stack_integration.config import Settings
from stack_integration.contracts.models import RunStatus
from stack_integration.controller import CollaborationController


def make_repo(path: Path):
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "README.md").write_text("fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-qm",
            "base",
        ],
        cwd=path,
        check=True,
    )


def test_terminal_run_cannot_resume(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    settings = Settings.load(tmp_path / "state")
    controller = CollaborationController(settings)
    try:
        run = controller.create_run(repo, "objective", ["REQ-1"])
    finally:
        controller.close()

    _set_status(run.id, RunStatus.CANCELLED, settings.state_root)
    with pytest.raises(typer.BadParameter, match="invalid run transition"):
        _set_status(run.id, RunStatus.ACTIVE, settings.state_root)


def _invoke(*args: str):
    import json as _json  # noqa: F401

    from typer.testing import CliRunner

    from stack_integration.cli import app

    return CliRunner().invoke(app, list(args))


def _spec(tmp_path: Path, payload: dict) -> Path:
    import json

    target = tmp_path / f"spec-{len(list(tmp_path.glob('spec-*')))}.json"
    target.write_text(json.dumps(payload))
    return target


def test_plan_rejects_bad_specs_without_tracebacks(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    state = str(tmp_path / "state")
    cases = {
        "unknown fields": {"objective": "o", "acceptance": ["A"], "tasks": [], "taks": []},
        "at least one task": {"objective": "o", "acceptance": ["A"], "tasks": []},
        "no task covers": {
            "objective": "o",
            "acceptance": ["A", "B"],
            "tasks": [{"id": "t", "description": "d", "acceptance_ids": ["A"]}],
        },
        "missing required": {"objective": "o", "tasks": [{"description": "d"}]},
    }
    for expected, payload in cases.items():
        result = _invoke("plan", str(_spec(tmp_path, payload)), str(repo), "--state", state)
        assert result.exit_code == 2, (expected, result.output)
        assert expected in result.output
        assert "Traceback" not in result.output


def test_failed_admission_cancels_the_orphan_run(tmp_path: Path):
    repo = tmp_path / "repo"
    make_repo(repo)
    state = tmp_path / "state"
    payload = {
        "objective": "o",
        "acceptance": ["A"],
        "tasks": [{"id": "t", "description": "d", "dependencies": ["ghost"]}],
    }
    result = _invoke("plan", str(_spec(tmp_path, payload)), str(repo), "--state", str(state))
    assert result.exit_code == 2
    assert "unknown dependencies" in result.output
    controller = CollaborationController(Settings.load(state))
    try:
        (run,) = controller.list_runs()
        assert run.status == RunStatus.CANCELLED
    finally:
        controller.close()


def test_plan_budget_runs_listing_status_steer_and_task_actions(tmp_path: Path):
    import json

    repo = tmp_path / "repo"
    make_repo(repo)
    (repo / "scratch.txt").write_text("uncommitted\n")
    state = str(tmp_path / "state")
    payload = {
        "objective": "o",
        "acceptance": ["A"],
        "budget": {"max_sessions": 2, "wall_time_seconds": 600},
        "tasks": [{"id": "t", "description": "d", "provider": "claude"}],
    }
    result = _invoke("plan", str(_spec(tmp_path, payload)), str(repo), "--state", state)
    assert result.exit_code == 0, result.output
    planned = json.loads(result.output)
    run_id = planned["run"]["id"]
    assert planned["run"]["budget"]["max_sessions"] == 2
    assert "uncommitted" in planned["warnings"][0]

    listing = _invoke("runs", "--state", state)
    assert listing.exit_code == 0 and run_id in listing.output

    steer = _invoke("steer", run_id, "focus on tests", "--task", "t", "--state", state)
    assert steer.exit_code == 0, steer.output
    assert json.loads(steer.output)["task_id"] == "t"

    retry = _invoke("task", "retry", "t", "--state", state)
    assert retry.exit_code == 2 and "can be requeued" in retry.output
    cancelled = _invoke("task", "cancel", "t", "--state", state)
    assert json.loads(cancelled.output)["status"] == "cancelled"

    status = _invoke("status", run_id, "--state", state)
    assert status.exit_code == 0 and "cancelled" in status.output
    missing = _invoke("status", "run_missing", "--state", state)
    assert missing.exit_code == 2 and "record not found" in missing.output
    assert _invoke("inspect", "task", "t", "--state", state).exit_code == 0
    assert _invoke("--version").output.startswith("stack-agent ")


def test_checked_in_schemas_match_the_models():
    from stack_integration.cli.main import SCHEMA_MODELS, render_schema

    root = Path(__file__).resolve().parents[1] / "docs" / "schemas"
    stale = [
        model.__name__
        for model in SCHEMA_MODELS
        if (root / f"{model.__name__.lower()}.schema.json").read_text() != render_schema(model)
    ]
    assert not stale, f"regenerate with `stack-agent schemas docs/schemas`: {stale}"


def test_serve_refuses_non_loopback_listeners(tmp_path: Path):
    """The dashboard and API are local only: any non-loopback host is rejected by policy
    before a server is started."""
    for host in ("0.0.0.0", "192.168.1.20", "example.com"):
        result = _invoke("serve", "--host", host, "--state", str(tmp_path / "state"))
        assert result.exit_code == 2, (host, result.output)
        assert "remote listeners are disabled" in result.output
