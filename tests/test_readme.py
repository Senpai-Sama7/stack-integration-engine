"""Keep README.md honest: every link, command, cited test, and example it shows must be real."""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest
import typer.main
from typer.testing import CliRunner

from stack_integration.cli import app
from stack_integration.config import Settings
from stack_integration.contracts.models import ALLOWED_TASK_TRANSITIONS, RunStatus, TaskStatus
from stack_integration.controller import CollaborationController

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
ASSETS = ROOT / "docs" / "assets"
TEXT = README.read_text(encoding="utf-8")

FENCE = re.compile(r"^```", re.MULTILINE)


def _prose(text: str) -> str:
    """README text with fenced code blocks removed."""
    parts = FENCE.split(text)
    return "".join(parts[0::2])


def _fenced(text: str, language: str | None = None) -> list[str]:
    blocks = re.findall(r"^```(\S*)\n(.*?)^```", text, flags=re.MULTILINE | re.DOTALL)
    return [body for lang, body in blocks if language is None or lang == language]


def _slug(heading: str) -> str:
    """GitHub's heading anchor: strip markup, lowercase, drop punctuation, spaces to hyphens."""
    heading = re.sub(r"`([^`]*)`", r"\1", heading)
    heading = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", heading)
    heading = re.sub(r"<[^>]+>", "", heading)
    heading = heading.replace("*", "")
    heading = heading.strip().lower()
    heading = re.sub(r"[^\w\- ]", "", heading)
    return heading.replace(" ", "-")


def _slugs(markdown: str) -> set[str]:
    return {
        _slug(match.group(1))
        for match in re.finditer(r"^#{1,6}\s+(.+?)\s*#*\s*$", _prose(markdown), flags=re.MULTILINE)
    }


def _relative_targets() -> list[str]:
    """Every relative link, image, and srcset target in the README."""
    targets = re.findall(r"\]\(([^)\s]+)\)", TEXT)
    targets += re.findall(r'(?:href|src)="([^"]+)"', TEXT)
    return [t for t in targets if not re.match(r"^(https?:|mailto:)", t)]


def test_relative_links_and_images_resolve():
    targets = _relative_targets()
    assert targets, "README should link to something"
    for target in targets:
        if target.startswith("#"):
            continue
        path, _, fragment = target.partition("#")
        resolved = ROOT / path
        assert resolved.exists(), f"README links to a missing file: {target}"
        if fragment and resolved.suffix == ".md":
            slugs = _slugs(resolved.read_text(encoding="utf-8"))
            assert fragment in slugs, f"{path} has no heading for #{fragment}"


def test_in_page_anchors_match_headings():
    slugs = _slugs(TEXT)
    anchors = [t[1:] for t in _relative_targets() if t.startswith("#")]
    assert anchors, "README should have in-page navigation"
    for anchor in anchors:
        assert anchor in slugs, f"README links to #{anchor} but no heading has that anchor"


def test_images_have_alt_text_and_assets_are_used_and_self_contained():
    for tag in re.findall(r"<img\b[^>]*>", TEXT):
        alt = re.search(r'alt="([^"]+)"', tag)
        assert alt and alt.group(1).strip(), f"image without alt text: {tag}"

    referenced = {Path(t).name for t in _relative_targets() if t.startswith("docs/assets/")}
    on_disk = {p.name for p in ASSETS.iterdir()}
    assert referenced == on_disk, f"unreferenced or missing assets: {referenced ^ on_disk}"

    for asset in ASSETS.iterdir():
        assert 0 < asset.stat().st_size < 400_000, f"{asset.name} is empty or oversized"
        if asset.suffix != ".svg":
            continue
        svg = asset.read_text(encoding="utf-8")
        root = ET.fromstring(svg)  # well-formed
        assert root.tag.endswith("svg")
        assert "<script" not in svg and "@import" not in svg, asset.name
        assert not re.search(r"""(?:href|src)=["']https?:|url\(\s*["']?https?:""", svg), (
            f"{asset.name} fetches an external resource"
        )


def test_readme_uses_no_em_dashes():
    assert chr(0x2014) not in TEXT, "house style: no em dashes in the README"


def _real_commands() -> set[str]:
    click_app = typer.main.get_command(app)
    return {name for name, command in click_app.commands.items() if not command.hidden}  # type: ignore[attr-defined]


def test_every_command_in_the_readme_exists_and_every_command_is_documented():
    real = _real_commands()

    used = set(re.findall(r"stack-agent\s+([a-z][a-z-]*)\b", "\n".join(_fenced(TEXT, "bash"))))
    assert used, "README should show commands"
    assert used <= real, f"README runs commands that do not exist: {used - real}"

    section = TEXT.split("## Command reference", 1)[1].split("\n## ", 1)[0]
    documented = set()
    for row in re.findall(r"^\|\s*((?:[^|\\]|\\.)+?)\s*\|", section, flags=re.MULTILINE):
        for span in re.findall(r"`([^`]+)`", row):
            first = span.split()[0]
            if re.fullmatch(r"[a-z][a-z-]*", first):
                documented.add(first)
    assert documented == real, (
        f"undocumented: {sorted(real - documented)}; nonexistent: {sorted(documented - real)}"
    )


def test_cited_tests_exist():
    cited = re.findall(r"\[`(test_\w+)`\]\((tests/[\w/]+\.py)\)", TEXT)
    assert len(cited) >= 25, "the trust table should cite its proof"
    defined: dict[str, set[str]] = {}
    for name, rel in cited:
        if rel not in defined:
            tree = ast.parse((ROOT / rel).read_text(encoding="utf-8"))
            defined[rel] = {
                node.name
                for node in ast.walk(tree)
                if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
            }
        assert name in defined[rel], f"README cites {rel}::{name}, which does not exist"
    assert len(set(cited)) == len(cited), "a test is cited twice"


def test_cited_source_files_exist():
    for rel in re.findall(r"\]\((stack_integration/[\w/]+(?:\.py)?)\)", TEXT):
        assert (ROOT / rel).exists(), rel


def test_lifecycle_diagram_matches_the_state_machine():
    (diagram,) = [b for b in _fenced(TEXT, "mermaid") if "stateDiagram" in b]
    drawn = {
        (src, dst)
        for src, dst in re.findall(r"^\s*(\w+)\s+-->\s+(\w+)\s*$", diagram, flags=re.MULTILINE)
    }
    actual = {
        (src.value, dst.value)
        for src, targets in ALLOWED_TASK_TRANSITIONS.items()
        for dst in targets
        if dst != TaskStatus.CANCELLED
    }
    assert drawn == actual, f"missing: {sorted(actual - drawn)}; extra: {sorted(drawn - actual)}"
    # The README says where cancelled is reachable from; keep that sentence true too.
    sentence = re.search(r"`cancelled` is a terminal state reachable from (.+?)\.", TEXT, re.DOTALL)
    assert sentence
    named = set(re.findall(r"`(\w+)`", sentence.group(1)))
    reachable = {
        src.value
        for src, targets in ALLOWED_TASK_TRANSITIONS.items()
        if TaskStatus.CANCELLED in targets
    }
    assert named == reachable


def _make_repo(path: Path) -> None:
    path.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=path, check=True)
    (path / "README.md").write_text("fixture\n")
    subprocess.run(["git", "add", "README.md"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=t@example.com", "commit", "-qm", "base"],
        cwd=path,
        check=True,
    )


def test_example_specs_in_the_readme_pass_planning(tmp_path: Path):
    specs = [b for b in _fenced(TEXT, "json") if '"objective"' in b]
    assert specs, "README should show a plan spec"
    specs.append((ROOT / "examples" / "local-review.json").read_text(encoding="utf-8"))
    for index, spec in enumerate(specs):
        repo = tmp_path / f"repo{index}"
        _make_repo(repo)
        target = tmp_path / f"spec{index}.json"
        target.write_text(json.dumps(json.loads(spec)))
        result = CliRunner().invoke(
            app, ["plan", str(target), str(repo), "--state", str(tmp_path / f"state{index}")]
        )
        assert result.exit_code == 0, result.output


def test_seed_demo_produces_the_runs_the_readme_shows(tmp_path: Path):
    state = tmp_path / "demo"
    done = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "seed_demo.py"), "--state", str(state)],
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert done.returncode == 0, done.stdout + done.stderr

    controller = CollaborationController(Settings.load(state))
    try:
        runs = controller.list_runs()
    finally:
        controller.close()
    assert {run.status for run in runs} == {
        RunStatus.COMPLETED,
        RunStatus.BLOCKED,
        RunStatus.FAILED,
        RunStatus.PAUSED,
    }
    assert all(run.objective.startswith("Demo:") for run in runs)

    refused = subprocess.run(
        [sys.executable, str(ROOT / "examples" / "seed_demo.py"), "--state", str(state)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert refused.returncode != 0, "seeding a non-empty state directory must not clobber it"

    # --force replaces a seeded directory but never an arbitrary one.
    stranger = tmp_path / "precious"
    stranger.mkdir()
    (stranger / "keep.txt").write_text("do not delete\n")
    forced = subprocess.run(
        [
            sys.executable,
            str(ROOT / "examples" / "seed_demo.py"),
            "--state",
            str(stranger),
            "--force",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert forced.returncode != 0 and (stranger / "keep.txt").exists()


@pytest.mark.parametrize("name", ["hero.svg", "flow.svg"])
def test_diagram_svgs_have_accessible_titles(name: str):
    root = ET.fromstring((ASSETS / name).read_text(encoding="utf-8"))
    ns = "{http://www.w3.org/2000/svg}"
    assert (root.findtext(f"{ns}title") or "").strip()
    assert (root.findtext(f"{ns}desc") or "").strip()
