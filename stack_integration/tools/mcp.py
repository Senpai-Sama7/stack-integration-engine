"""Minimal MCP stdio client used for pinned local tool servers."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import Any

from stack_integration import __version__

# asyncio's default stream limit is 64 KiB per line, which a NEXUS context pack or search
# result easily exceeds. Responses are one JSON line each, so cap them well above any
# legitimate payload but below anything that could exhaust memory.
MCP_LINE_LIMIT_BYTES = 16 * 1024 * 1024
STDERR_LINE_CHARS = 2000
STDERR_LINES_KEPT = 200


class McpProtocolError(RuntimeError):
    pass


class McpStdioClient:
    def __init__(
        self,
        command: list[str],
        *,
        cwd: str | Path,
        env: dict[str, str] | None = None,
        timeout: float = 30,
        line_limit: int = MCP_LINE_LIMIT_BYTES,
    ):
        self.line_limit = line_limit
        self.command = command
        self.cwd = Path(cwd)
        self.env = env or {}
        self.timeout = timeout
        self.process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()
        self._stderr_task: asyncio.Task[None] | None = None
        self.stderr: list[str] = []

    async def start(self) -> McpStdioClient:
        try:
            self.process = await asyncio.create_subprocess_exec(
                *self.command,
                cwd=self.cwd,
                env={**os.environ, **self.env},
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                limit=self.line_limit,
            )
            self._stderr_task = asyncio.create_task(self._drain_stderr())
            await self.request(
                "initialize",
                {
                    "protocolVersion": "2025-06-18",
                    "capabilities": {},
                    "clientInfo": {"name": "stack-integration-engine", "version": __version__},
                },
            )
            await self.notify("notifications/initialized", {})
            return self
        except Exception:
            await self.close()
            raise

    async def _drain_stderr(self) -> None:
        """Keep a bounded tail of the server's stderr for error messages.

        Reads chunks rather than lines: a server that logs one huge unterminated line
        must neither raise inside this task nor fill the pipe and block the server.
        """
        assert self.process and self.process.stderr
        pending = b""
        try:
            while chunk := await self.process.stderr.read(64 * 1024):
                *lines, pending = (pending + chunk).split(b"\n")
                for line in lines:
                    self._record_stderr(line)
                pending = pending[-STDERR_LINE_CHARS * 4 :]
            if pending:
                self._record_stderr(pending)
        except Exception:
            # Diagnostics only: never let them take the client down.
            return

    def _record_stderr(self, line: bytes) -> None:
        self.stderr.append(line.decode(errors="replace")[:STDERR_LINE_CHARS].rstrip())
        del self.stderr[:-STDERR_LINES_KEPT]

    async def notify(self, method: str, params: dict[str, Any]) -> None:
        await self._write({"jsonrpc": "2.0", "method": method, "params": params})

    async def request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        async with self._lock:
            self._request_id += 1
            request_id = self._request_id
            await self._write(
                {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}
            )
            assert self.process and self.process.stdout
            while True:
                try:
                    line = await asyncio.wait_for(self.process.stdout.readline(), self.timeout)
                except TimeoutError as error:
                    raise McpProtocolError(f"timeout waiting for {method}") from error
                except (ValueError, asyncio.LimitOverrunError) as error:
                    # StreamReader.readline raises ValueError past the limit; the stream
                    # position is then unreliable, so the exchange cannot continue.
                    raise McpProtocolError(
                        f"MCP response to {method} exceeded the {self.line_limit}-byte line limit"
                    ) from error
                if not line:
                    detail = "\n".join(self.stderr[-10:])
                    raise McpProtocolError(f"MCP server exited while handling {method}: {detail}")
                try:
                    message = json.loads(line)
                except json.JSONDecodeError as error:
                    raise McpProtocolError("MCP server emitted malformed JSON") from error
                if message.get("id") != request_id:
                    continue
                if "error" in message:
                    raise McpProtocolError(f"MCP error: {message['error']}")
                result = message.get("result")
                if not isinstance(result, dict):
                    raise McpProtocolError("MCP response result must be an object")
                return result

    async def _write(self, message: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin or self.process.returncode is not None:
            raise McpProtocolError("MCP server is not running")
        self.process.stdin.write(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        await self.process.stdin.drain()

    async def list_tools(self) -> list[dict[str, Any]]:
        result = await self.request("tools/list", {})
        tools = result.get("tools")
        if not isinstance(tools, list):
            raise McpProtocolError("tools/list did not return a tool list")
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return await self.request("tools/call", {"name": name, "arguments": arguments})

    async def close(self) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), 3)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
        if self._stderr_task:
            with contextlib.suppress(Exception):
                await self._stderr_task

    async def __aenter__(self) -> McpStdioClient:
        return await self.start()

    async def __aexit__(self, *_: object) -> None:
        await self.close()
