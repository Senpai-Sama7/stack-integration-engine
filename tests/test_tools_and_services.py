import json
import os
import stat
import sys
from pathlib import Path

import pytest

from stack_integration.contracts.models import CapabilityStatus
from stack_integration.core.types import ClaimBundle, GateDecision
from stack_integration.providers.claude import ClaudeAdapter
from stack_integration.providers.codex import CodexAdapter
from stack_integration.providers.process import ProcessResult
from stack_integration.services import CapabilityUnavailableError
from stack_integration.services.nexus_adapter import NexusAdapter
from stack_integration.services.platform_adapter import PlatformAdapter
from stack_integration.services.prometheus_adapter import PrometheusAdapter
from stack_integration.services.sage_adapter import SageAdapter
from stack_integration.services.sdlc_adapter import SDLCAdapter
from stack_integration.tools import SdlcToolAdapter


def fake_cli(tmp_path: Path, name: str, responses: dict[str, tuple[int, str]]) -> str:
    """Write an executable that answers argument lines from ``responses``."""
    script = tmp_path / name
    script.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"responses = json.loads({json.dumps(json.dumps(responses))})\n"
        "code, text = responses.get(' '.join(sys.argv[1:]), (2, 'unknown arguments'))\n"
        "print(text)\n"
        "sys.exit(code)\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IXUSR)
    return str(script)


@pytest.mark.asyncio
async def test_claude_probe_reports_features_and_authentication(tmp_path):
    help_text = "--output-format --json-schema --resume --agents --background --worktree"
    executable = fake_cli(
        tmp_path,
        "claude",
        {
            "--version": (0, "2.1.292 (Claude Code)"),
            "--help": (0, help_text),
            "auth status": (0, json.dumps({"loggedIn": True})),
        },
    )
    capability = await ClaudeAdapter(executable).probe()
    assert capability.status == CapabilityStatus.SUPPORTED
    assert capability.version == "2.1.292 (Claude Code)"
    assert capability.features["authentication"] == CapabilityStatus.SUPPORTED

    logged_out = fake_cli(
        tmp_path,
        "claude-out",
        {
            "--version": (0, "2.1.292"),
            "--help": (0, help_text),
            "auth status": (1, json.dumps({"loggedIn": False})),
        },
    )
    degraded = await ClaudeAdapter(logged_out).probe()
    assert degraded.status == CapabilityStatus.DEGRADED
    assert (await ClaudeAdapter(str(tmp_path / "absent")).probe()).status == (
        CapabilityStatus.UNSUPPORTED
    )


@pytest.mark.asyncio
async def test_codex_probe_requires_structured_output_and_login(tmp_path):
    exec_help = "--json --output-schema resume --worktree"
    executable = fake_cli(
        tmp_path,
        "codex",
        {
            "--version": (0, "codex-cli 0.154.0"),
            "--help": (0, "exec app-server"),
            "exec --help": (0, exec_help),
            "login status": (0, "Logged in using ChatGPT"),
        },
    )
    capability = await CodexAdapter(executable).probe()
    assert capability.status == CapabilityStatus.SUPPORTED
    assert capability.features["app_server"] == CapabilityStatus.SUPPORTED

    old = fake_cli(
        tmp_path,
        "codex-old",
        {
            "--version": (0, "codex-cli 0.1"),
            "--help": (0, "exec"),
            "exec --help": (0, "--json"),
            "login status": (0, "Logged in"),
        },
    )
    degraded = await CodexAdapter(old).probe()
    assert degraded.status == CapabilityStatus.DEGRADED
    assert degraded.features["output_schema"] == CapabilityStatus.UNSUPPORTED


def test_provider_failure_states_never_complete():
    def process(**flags):
        values = {
            "args": ("x",),
            "exit_code": 1,
            "stdout": b"",
            "stderr": b"boom",
            "duration_ms": 1,
        }
        return ProcessResult(**{**values, **flags})

    for adapter in (CodexAdapter, ClaudeAdapter):
        assert adapter.parse_result(process(cancelled=True)).status == "cancelled"
        assert adapter.parse_result(process(launch_error=True)).status == "failed"
        assert adapter.parse_result(process(truncated=True)).status == "protocol_error"
    assert ClaudeAdapter.parse_result(process(stdout=b"[1]")).status == "protocol_error"
    failed = CodexAdapter.parse_result(
        process(
            exit_code=1,
            stdout=b'{"type":"thread.started","thread_id":"t"}\n'
            b'{"type":"turn.failed","message":"quota exhausted"}\n',
        )
    )
    assert failed.status == "failed"
    assert failed.error == "quota exhausted"


class FakeSupervisor:
    def __init__(self, result: ProcessResult):
        self.result = result
        self.calls: list[list[str]] = []

    async def run(self, args, **_):
        self.calls.append(list(args))
        if args[-1] == "--version":
            return ProcessResult(tuple(args), 0, b"1.3.1", b"", 1)
        return self.result


def sdlc_result(stdout: bytes, exit_code: int = 0, truncated: bool = False) -> ProcessResult:
    return ProcessResult(("sdlc",), exit_code, stdout, b"", 1, truncated=truncated)


@pytest.mark.asyncio
async def test_sdlc_adapter_enforces_read_only_json_contract(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/sdlc")
    supervisor = FakeSupervisor(sdlc_result(b'{"risk": "low"}', exit_code=1))
    adapter = SdlcToolAdapter(supervisor=supervisor, source_script=tmp_path / "none.py")
    assert (await adapter.probe())["status"] == "supported"
    payload = await adapter.run_read_only("risk", project_root=tmp_path)
    assert payload == {"risk": "low", "_controller_exit_code": 1}
    assert supervisor.calls[-1][:3] == ["/usr/bin/sdlc", "risk", "--path"]
    with pytest.raises(PermissionError):
        await adapter.run_read_only("deploy", project_root=tmp_path)
    for result, message in [
        (sdlc_result(b"not json"), "invalid JSON"),
        (sdlc_result(b"[]"), "JSON object"),
        (sdlc_result(b"{}", exit_code=2), "failed"),
        (sdlc_result(b"{}", truncated=True), "exceeded"),
    ]:
        supervisor.result = result
        with pytest.raises(RuntimeError, match=message):
            await adapter.run_read_only("snapshot", project_root=tmp_path)


@pytest.mark.asyncio
async def test_sdlc_probe_reports_unsupported_without_launcher(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)
    adapter = SdlcToolAdapter(source_script=tmp_path / "missing.py")
    assert (await adapter.probe())["status"] == "unsupported"
    with pytest.raises(RuntimeError):
        await adapter.run_read_only("snapshot", project_root=tmp_path)


@pytest.mark.asyncio
async def test_compatibility_services_fail_closed(tmp_path):
    bundle = ClaimBundle(origin_agent="test")
    for call in [
        SageAdapter().create_saga("s", []),
        SageAdapter().execute_saga("s", {}),
        SageAdapter().rollback_saga("e"),
        PlatformAdapter().query("q"),
        PlatformAdapter().get_task_status("t"),
        PlatformAdapter().approve_action("a"),
        PrometheusAdapter().evaluate_gates(bundle),
        PrometheusAdapter().record_decision(bundle, GateDecision.APPROVE),
        PrometheusAdapter().audit_log(),
    ]:
        with pytest.raises(CapabilityUnavailableError):
            await call
    for adapter in (SageAdapter(), PlatformAdapter(), PrometheusAdapter(), SDLCAdapter()):
        assert await adapter.close() is None
    with pytest.raises(FileNotFoundError):
        NexusAdapter(str(tmp_path), server_script=str(tmp_path / "missing.js"))
    script = tmp_path / "server.js"
    script.write_text("")
    nexus = NexusAdapter(str(tmp_path), server_script=str(script))
    with pytest.raises(PermissionError, match="independent verification"):
        await nexus.test_run()
    assert await nexus.close() is None


@pytest.mark.asyncio
async def test_sdlc_service_wrapper_delegates(tmp_path, monkeypatch):
    calls = []

    async def fake_run(self, command, *, project_root, **_):
        calls.append((command, project_root))
        return {"command": command}

    monkeypatch.setattr(SdlcToolAdapter, "run_read_only", fake_run)
    adapter = SDLCAdapter()
    assert (await adapter.repo_snapshot("p"))["command"] == "snapshot"
    assert (await adapter.secret_scan("p"))["command"] == "secret-scan"
    assert (await adapter.risk_score("p"))["command"] == "risk"
    assert [item[0] for item in calls] == ["snapshot", "secret-scan", "risk"]
    assert os.path.basename(str(calls[0][1])) == "p"
