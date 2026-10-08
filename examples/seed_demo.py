#!/usr/bin/env python3
"""Seed a state directory with realistic runs so you can explore the dashboard and CLI.

    python examples/seed_demo.py --state /tmp/stack-agent-demo
    stack-agent runs   --state /tmp/stack-agent-demo
    stack-agent serve  --state /tmp/stack-agent-demo

No model is called and no quota is spent. The real controller runs end to end (task
leases, isolated Git worktrees, path-scope enforcement, opposite-provider review bound to
the candidate hash, independent pytest checks, serialized integration), but the "Codex" and
"Claude" workers are deterministic simulators defined in this file. Every run objective is
prefixed "Demo:" so seeded data can never be mistaken for real evidence.

Needs the dev extra for pytest: pip install -e '.[dev,api]'
"""

from __future__ import annotations

import argparse
import asyncio
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from stack_integration.config import Settings
from stack_integration.contracts.models import (
    Capability,
    CapabilityStatus,
    CheckDefinition,
    Provider,
    ProviderRequest,
    ProviderResult,
    Run,
    RunStatus,
)
from stack_integration.controller import CollaborationController
from stack_integration.providers.base import ProviderAdapter

MARKER = ".seed-demo"

PYTEST_CHECK = CheckDefinition(
    id="pytest",
    name="Unit tests",
    command=[sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"],
    timeout_seconds=120,
    expects_tests=True,
)

SLUGIFY = '''"""Turn text into URL-safe slugs."""

import re


def slugify(text: str) -> str:
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")
'''

BASE_FILES = {
    "textkit/__init__.py": 'from .slugify import slugify\n\n__all__ = ["slugify"]\n',
    "textkit/slugify.py": SLUGIFY,
    "tests/test_slugify.py": (
        "from textkit import slugify\n\n\n"
        "def test_basic():\n    assert slugify('Hello, World!') == 'hello-world'\n\n\n"
        "def test_collapses_runs():\n    assert slugify('a   b___c') == 'a-b-c'\n\n\n"
        "def test_trims_dashes():\n    assert slugify('--x--') == 'x'\n"
    ),
    "pyproject.toml": '[project]\nname = "textkit"\nversion = "0.1.0"\n',
    "README.md": "# textkit\n\nSmall text utilities.\n",
}

# What each simulated builder writes, by task ID (paths relative to the project root).
BUILDS: dict[str, dict[str, str]] = {
    "validate-input": {
        "textkit/slugify.py": SLUGIFY.replace(
            "def slugify(text: str) -> str:\n",
            "def slugify(text: str) -> str:\n"
            "    if not isinstance(text, str):\n"
            '        raise TypeError(f"slugify expects str, got {type(text).__name__}")\n',
        ),
        "tests/test_validation.py": (
            "import pytest\n\nfrom textkit import slugify\n\n\n"
            "@pytest.mark.parametrize('value', [None, 3, b'bytes', ['a']])\n"
            "def test_rejects_non_strings(value):\n"
            "    with pytest.raises(TypeError):\n        slugify(value)\n"
        ),
    },
    "add-cli": {
        "textkit/cli.py": (
            "import argparse\n\nfrom .slugify import slugify\n\n\n"
            "def main(argv=None) -> int:\n"
            "    parser = argparse.ArgumentParser(prog='textkit')\n"
            "    parser.add_argument('text')\n"
            "    print(slugify(parser.parse_args(argv).text))\n"
            "    return 0\n"
        ),
        "tests/test_cli.py": (
            "from textkit.cli import main\n\n\n"
            "def test_cli_prints_slug(capsys):\n"
            "    assert main(['Hello World']) == 0\n"
            "    assert capsys.readouterr().out.strip() == 'hello-world'\n"
        ),
    },
    "write-usage-docs": {
        "docs/USAGE.md": (
            "# Using textkit\n\n```python\nfrom textkit import slugify\n\n"
            "slugify('Hello, World!')  # 'hello-world'\n```\n\n"
            "```console\n$ python -m textkit.cli 'Hello World'\nhello-world\n```\n"
        ),
    },
    "load-toml": {
        "textkit/settings.py": (
            "import tomllib\nfrom pathlib import Path\n\n\n"
            "def load(path):\n"
            "    try:\n        return tomllib.loads(Path(path).read_text())\n"
            "    except tomllib.TOMLDecodeError:\n        return {}\n"
        ),
        "tests/test_settings.py": (
            "from textkit.settings import load\n\n\n"
            "def test_load(tmp_path):\n"
            "    path = tmp_path / 's.toml'\n    path.write_text('a = 1')\n"
            "    assert load(path) == {'a': 1}\n"
        ),
    },
    "retry-helper": {
        "textkit/retry.py": (
            "import time\n\n\n"
            "def retry(fn, attempts=3, delay=0.1):\n"
            "    for attempt in range(attempts):\n"
            "        try:\n            return fn()\n"
            "        except OSError:\n"
            "            if attempt == attempts - 1:\n                raise\n"
            "            time.sleep(delay)\n"
        ),
        # Outside the task's allowed paths: the controller must refuse this candidate.
        "textkit/__init__.py": "from .slugify import slugify\nfrom .retry import retry\n",
    },
}

# (verdict, summary, findings) per reviewed task, in order of attempts.
REVIEWS: dict[str, list[tuple[str, str, list[tuple[str, str]]]]] = {
    "validate-input": [("approve", "Rejects non-strings; tests cover the boundary.", [])],
    "add-cli": [
        (
            "approve",
            "Thin wrapper over slugify; behavior covered by a capsys test.",
            [("info", "Consider --version and a console_scripts entry in a follow-up.")],
        )
    ],
    "write-usage-docs": [("approve", "Examples match the implemented API.", [])],
    "load-toml": [
        (
            "request_changes",
            "A malformed file is silently treated as empty configuration.",
            [
                (
                    "medium",
                    "load() swallows tomllib.TOMLDecodeError and returns {}, so a typo in the "
                    "settings file silently resets every option to its default.",
                ),
                ("low", "No test covers a missing file or malformed TOML."),
            ],
        ),
        (
            "request_changes",
            "The error is still hidden and the failure path is untested.",
            [
                (
                    "high",
                    "The exception is now logged but still swallowed: callers cannot tell a "
                    "valid empty file from a corrupt one. Raise a SettingsError that names the "
                    "file and the offending line.",
                ),
            ],
        ),
    ],
}

USAGE = {
    Provider.CODEX: {"input_tokens": 41_230, "output_tokens": 3_120},
    Provider.CLAUDE: {"input_tokens": 18_400, "output_tokens": 2_210, "total_cost_usd": 0.0831},
}


class DemoAdapter(ProviderAdapter):
    """A deterministic stand-in for a provider CLI. It never calls a model."""

    def __init__(self, provider: Provider):
        super().__init__("demo")
        self.provider = provider
        self.sessions = 0
        self.review_attempts: dict[str, int] = {}

    async def probe(self) -> Capability:
        return Capability(
            id=f"provider.{self.provider.value}",
            provider=self.provider,
            executable="demo",
            status=CapabilityStatus.SUPPORTED,
            detail="simulated provider from examples/seed_demo.py",
        )

    async def execute(self, request: ProviderRequest) -> ProviderResult:
        self.sessions += 1
        if request.role.value == "reviewer":
            structured = self._review(request)
        else:
            structured = self._build(request)
        return ProviderResult(
            provider=self.provider,
            status="completed",
            session_id=f"demo-{self.provider.value}-{self.sessions:03d}",
            output=structured["summary"],
            structured_output=structured,
            exit_code=0,
            duration_ms=12_000 + 3_000 * self.sessions,
            usage=dict(USAGE[self.provider]),
        )

    def _build(self, request: ProviderRequest) -> dict[str, Any]:
        root = Path(request.project_root)
        written = []
        if not request.read_only:
            for relative, content in BUILDS.get(request.task_id, {}).items():
                target = root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content)
                written.append(relative)
        return {
            "summary": (
                f"Simulated worker finished {request.task_id}"
                + (f" and wrote {len(written)} file(s)." if written else " (read only).")
            ),
            "changed_paths": written,
            "requirements_addressed": [],
            "known_limitations": ["Simulated by examples/seed_demo.py; no model was called."],
        }

    def _review(self, request: ProviderRequest) -> dict[str, Any]:
        coverage = re.search(r"Acceptance: (\[.*?\])", request.prompt)
        acceptance = re.findall(r"'([^']+)'", coverage.group(1)) if coverage else []
        attempt = self.review_attempts.get(request.task_id, 0)
        self.review_attempts[request.task_id] = attempt + 1
        script = REVIEWS.get(request.task_id) or [("approve", "Looks correct.", [])]
        verdict, summary, findings = script[min(attempt, len(script) - 1)]
        return {
            "verdict": verdict,
            "summary": summary,
            "requirement_coverage": acceptance if verdict == "approve" else [],
            "findings": [{"severity": s, "statement": text} for s, text in findings],
        }


def git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "user.name=Demo", "-c", "user.email=demo@example.com", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
    )


def make_demo_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    git(path, "init", "-q")
    for relative, content in BASE_FILES.items():
        target = path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content)
    git(path, "add", "-A")
    git(path, "commit", "-qm", "textkit: initial slugify")
    return path


def task(
    task_id: str,
    description: str,
    provider: str,
    *,
    dependencies: list[str] | None = None,
    paths: list[str] | None = None,
    acceptance: list[str] | None = None,
) -> dict[str, Any]:
    definition: dict[str, Any] = {
        "id": task_id,
        "description": description,
        "provider": provider,
        "dependencies": dependencies or [],
    }
    if paths is not None:
        definition["side_effect"] = "worktree_write"
        definition["allowed_paths"] = paths
    if acceptance is not None:
        definition["acceptance_ids"] = acceptance
    return definition


async def seed(state: Path) -> None:
    repo = make_demo_repo(state / "demo-repo")
    providers = {provider: DemoAdapter(provider) for provider in Provider}
    controller = CollaborationController(Settings.load(state), providers=providers)
    controller.dispatch_poll_seconds = 0.05
    try:
        await run_completed(controller, repo)
        await run_blocked(controller, repo)
        await run_failed(controller, repo)
        plan_paused(controller, repo)
    finally:
        controller.close()


async def run_completed(controller: CollaborationController, repo: Path) -> None:
    run = controller.create_run(
        repo,
        "Demo: validate input, add CLI and docs",
        ["REQ-VALIDATION", "REQ-CLI", "REQ-DOCS"],
        checks=[PYTEST_CHECK],
    )
    controller.add_tasks(
        run.id,
        [
            task(
                "survey-edge-cases",
                "Read slugify and list the inputs it mishandles.",
                "claude",
                acceptance=["REQ-VALIDATION"],
            ),
            task(
                "validate-input",
                "Reject non-string input with a clear TypeError and cover it with tests.",
                "codex",
                dependencies=["survey-edge-cases"],
                paths=["textkit", "tests"],
                acceptance=["REQ-VALIDATION"],
            ),
            task(
                "add-cli",
                "Add a textkit command line that prints the slug of its argument.",
                "claude",
                dependencies=["survey-edge-cases"],
                paths=["textkit/cli.py", "tests/test_cli.py"],
                acceptance=["REQ-CLI"],
            ),
            task(
                "write-usage-docs",
                "Document the library call and the command line in docs/USAGE.md.",
                "codex",
                dependencies=["validate-input", "add-cli"],
                paths=["docs"],
                acceptance=["REQ-DOCS"],
            ),
            task(
                "final-review",
                "Read the combined result and confirm every requirement is met.",
                "claude",
                dependencies=["write-usage-docs"],
                acceptance=["REQ-VALIDATION", "REQ-CLI", "REQ-DOCS"],
            ),
        ],
    )
    done = await controller.execute_run(run.id)
    assert done.status == RunStatus.COMPLETED, done.status


async def run_blocked(controller: CollaborationController, repo: Path) -> None:
    run = controller.create_run(
        repo,
        "Demo: load settings from a TOML file",
        ["REQ-SETTINGS"],
        checks=[PYTEST_CHECK],
    )
    controller.add_tasks(
        run.id,
        [
            task(
                "load-toml",
                "Add a settings loader that reads a TOML file.",
                "codex",
                paths=["textkit/settings.py", "tests/test_settings.py"],
                acceptance=["REQ-SETTINGS"],
            )
        ],
    )
    done = await controller.execute_run(run.id)
    assert done.status == RunStatus.BLOCKED, done.status


async def run_failed(controller: CollaborationController, repo: Path) -> None:
    run = controller.create_run(
        repo, "Demo: retry transient network errors", ["REQ-RETRY"], checks=[PYTEST_CHECK]
    )
    controller.add_tasks(
        run.id,
        [
            task(
                "retry-helper",
                "Add a retry helper for OSError (touch only textkit/retry.py).",
                "claude",
                paths=["textkit/retry.py"],
                acceptance=["REQ-RETRY"],
            )
        ],
    )
    done = await controller.execute_run(run.id)
    assert done.status == RunStatus.FAILED, done.status


def plan_paused(controller: CollaborationController, repo: Path) -> None:
    run = controller.create_run(repo, "Demo: add a benchmark suite", ["REQ-BENCH"])
    controller.add_tasks(
        run.id,
        [
            task(
                "survey-hot-paths",
                "Profile slugify on long inputs.",
                "claude",
                acceptance=["REQ-BENCH"],
            ),
            task(
                "bench-suite",
                "Add pytest-benchmark cases for slugify.",
                "codex",
                dependencies=["survey-hot-paths"],
                paths=["benchmarks"],
                acceptance=["REQ-BENCH"],
            ),
        ],
    )
    current = controller.database.get("run", run.id, Run)
    current.status = RunStatus.PAUSED
    controller.database.save_run(current, expected_revision=current.revision)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--state", type=Path, required=True, help="state directory to create")
    parser.add_argument(
        "--force", action="store_true", help="replace a state directory this script created"
    )
    args = parser.parse_args(argv)
    state = args.state.expanduser().resolve()
    if state.exists() and any(state.iterdir()):
        if not args.force:
            parser.error(f"{state} is not empty; pass --force to replace it")
        if not (state / MARKER).exists():
            parser.error(f"refusing to delete {state}: it was not created by this script")
        shutil.rmtree(state)
    state.mkdir(parents=True, exist_ok=True)
    (state / MARKER).write_text("created by examples/seed_demo.py; safe to replace with --force\n")
    if shutil.which("git") is None:
        parser.error("git is required")
    asyncio.run(seed(state))
    print(f"Seeded 4 demo runs in {state}")
    print(f"  stack-agent runs  --state {state}")
    print(f"  stack-agent serve --state {state}   (token: {state / 'operator.token'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
