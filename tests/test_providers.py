import json
from pathlib import Path

import pytest

from stack_integration.contracts.models import ActorRole, ProviderRequest
from stack_integration.providers.claude import ClaudeAdapter
from stack_integration.providers.codex import CodexAdapter
from stack_integration.providers.process import ProcessResult


def process(stdout: str, exit_code=0, timed_out=False):
    return ProcessResult(("provider",), exit_code, stdout.encode(), b"", 12.0, timed_out)


def test_codex_requires_terminal_event():
    result = CodexAdapter.parse_result(
        process(json.dumps({"type": "thread.started", "thread_id": "t1"}))
    )
    assert result.status == "failed"
    assert "terminal completion" in (result.error or "")


def test_codex_parses_jsonl_and_usage():
    lines = [
        {"type": "thread.started", "thread_id": "t1"},
        {"type": "item.completed", "item": {"type": "agent_message", "text": '{"ok":true}'}},
        {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 3}},
    ]
    result = CodexAdapter.parse_result(process("\n".join(map(json.dumps, lines))))
    assert result.status == "completed"
    assert result.session_id == "t1"
    assert result.structured_output == {"ok": True}
    assert result.usage["input_tokens"] == 10


def test_malformed_codex_stream_is_protocol_error():
    assert CodexAdapter.parse_result(process("{broken")).status == "protocol_error"


def test_claude_distinguishes_success_and_error():
    success = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "session_id": "c1",
        "result": "done",
        "structured_output": {"ok": True},
        "usage": {"input_tokens": 5},
    }
    assert ClaudeAdapter.parse_result(process(json.dumps(success))).status == "completed"
    error = {**success, "is_error": True, "result": "permission denied"}
    assert ClaudeAdapter.parse_result(process(json.dumps(error), exit_code=1)).status == "failed"


def test_timeout_never_becomes_success():
    assert CodexAdapter.parse_result(process("", timed_out=True)).status == "timeout"
    assert ClaudeAdapter.parse_result(process("", timed_out=True)).status == "timeout"


class RecordingSupervisor:
    def __init__(self, provider):
        self.provider = provider
        self.calls = []

    async def run(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if self.provider == "codex":
            output = "\n".join(
                map(
                    json.dumps,
                    [
                        {"type": "thread.started", "thread_id": "thread"},
                        {"type": "turn.completed", "usage": {}},
                    ],
                )
            )
        else:
            output = json.dumps(
                {
                    "type": "result",
                    "subtype": "success",
                    "is_error": False,
                    "session_id": "session",
                    "result": "ok",
                }
            )
        return process(output)


@pytest.mark.asyncio
async def test_provider_commands_attach_bridge_without_token_in_arguments(tmp_path: Path):
    request = ProviderRequest(
        task_id="task",
        project_root=str(tmp_path),
        prompt="inspect",
        role=ActorRole.REVIEWER,
        read_only=True,
        session_id="resume-id",
        mcp_server_command=["python3", "-m", "stack_integration.cli", "bridge"],
        environment={"STACK_AGENT_GRANT": "sensitive-token"},
    )
    codex_process = RecordingSupervisor("codex")
    claude_process = RecordingSupervisor("claude")
    await CodexAdapter(supervisor=codex_process).execute(request)
    await ClaudeAdapter(supervisor=claude_process).execute(request)
    codex_args, codex_options = codex_process.calls[0]
    claude_args, claude_options = claude_process.calls[0]
    assert codex_args.index("exec") < codex_args.index("resume")
    assert "sensitive-token" not in " ".join(codex_args)
    assert "sensitive-token" not in " ".join(claude_args)
    assert codex_options["env"]["STACK_AGENT_GRANT"] == "sensitive-token"
    assert claude_options["env"]["STACK_AGENT_GRANT"] == "sensitive-token"
