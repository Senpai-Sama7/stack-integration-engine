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
