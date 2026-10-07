import sys

import pytest

from stack_integration.tools.mcp import McpProtocolError, McpStdioClient


@pytest.mark.asyncio
async def test_startup_failure_closes_process(tmp_path):
    client = McpStdioClient(
        [sys.executable, "-c", "import sys; sys.exit(1)"],
        cwd=tmp_path,
        timeout=0.2,
    )
    with pytest.raises(McpProtocolError):
        await client.start()
    assert client.process is None or client.process.returncode is not None


SERVER = [
    sys.executable,
    str(__import__("pathlib").Path(__file__).parent / "fixtures" / "fake_mcp_server.py"),
]


@pytest.mark.asyncio
async def test_client_negotiates_lists_and_calls_tools(tmp_path):
    async with McpStdioClient(SERVER, cwd=tmp_path, timeout=5) as client:
        tools = await client.list_tools()
        assert {tool["name"] for tool in tools} >= {"nexus_context_pack"}
        result = await client.call_tool("echo", {"value": 1})
        assert '"value": 1' in result["content"][0]["text"]
        with pytest.raises(McpProtocolError, match="MCP error"):
            await client.call_tool("fail", {})
        with pytest.raises(McpProtocolError, match="must be an object"):
            await client.call_tool("not_object", {})
    assert client.process is not None and client.process.returncode is not None


@pytest.mark.asyncio
async def test_client_reports_malformed_output_and_server_exit(tmp_path):
    async with McpStdioClient(SERVER, cwd=tmp_path, timeout=5) as client:
        with pytest.raises(McpProtocolError, match="malformed JSON"):
            await client.call_tool("malformed", {})
    async with McpStdioClient(SERVER, cwd=tmp_path, timeout=5) as client:
        with pytest.raises(McpProtocolError, match="exited"):
            await client.call_tool("exit", {})
        with pytest.raises(McpProtocolError, match="not running"):
            await client.call_tool("echo", {})


@pytest.mark.asyncio
async def test_nexus_adapter_admits_only_read_only_tools(tmp_path, monkeypatch):
    from stack_integration.tools import NexusToolAdapter

    script = tmp_path / "server.js"
    script.write_text("// placeholder; the client is redirected to the Python fixture\n")
    adapter = NexusToolAdapter(script)
    monkeypatch.setattr(
        adapter, "client", lambda workspace: McpStdioClient(SERVER, cwd=workspace, timeout=5)
    )
    probe = await adapter.probe(tmp_path)
    assert probe["status"] == "supported"
    assert "nexus_write_file" not in probe["read_only_tools"]
    result = await adapter.call_read_only(tmp_path, "nexus_workspace_overview", {})
    assert "nexus_workspace_overview" in NexusToolAdapter.content_text(result)
    with pytest.raises(PermissionError):
        await adapter.call_read_only(tmp_path, "nexus_write_file", {})
    with pytest.raises(McpProtocolError, match="unavailable"):
        await adapter.call_read_only(tmp_path, "nexus_search", {})
    with pytest.raises(FileNotFoundError):
        NexusToolAdapter(tmp_path / "missing.js")


@pytest.mark.asyncio
async def test_large_responses_and_stderr_lines_do_not_break_the_client(tmp_path):
    """asyncio's default 64 KiB line limit made any larger tool result (a NEXUS context
    pack, a search result) raise ValueError, and a long stderr line crashed close()."""
    async with McpStdioClient(SERVER, cwd=tmp_path, timeout=10) as client:
        result = await client.call_tool("big", {})
        assert len(result["content"][0]["text"]) == 300_000
        assert await client.call_tool("echo", {"after": "big"})
    assert all(len(line) <= 2000 for line in client.stderr)
    assert client.stderr


@pytest.mark.asyncio
async def test_response_over_the_configured_limit_is_a_protocol_error(tmp_path):
    async with McpStdioClient(SERVER, cwd=tmp_path, timeout=10, line_limit=100_000) as client:
        with pytest.raises(McpProtocolError, match="line limit"):
            await client.call_tool("big", {})
