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
