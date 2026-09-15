"""Bounded, cancellable subprocess supervision for providers and checks."""

from __future__ import annotations

import asyncio
import os
import signal
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProcessResult:
    args: tuple[str, ...]
    exit_code: int | None
    stdout: bytes
    stderr: bytes
    duration_ms: float
    timed_out: bool = False
    cancelled: bool = False
    truncated: bool = False
    launch_error: bool = False


class ProcessSupervisor:
    def __init__(self, *, output_limit_bytes: int = 10 * 1024 * 1024, kill_grace: float = 3.0):
        if output_limit_bytes < 1024:
            raise ValueError("output limit must be at least 1024 bytes")
        self.output_limit_bytes = output_limit_bytes
        self.kill_grace = kill_grace

    async def run(
        self,
        args: list[str],
        *,
        cwd: str | Path,
        timeout: float,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
    ) -> ProcessResult:
        if not args:
            raise ValueError("process command cannot be empty")
        started = time.monotonic()
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(cwd),
                env={**os.environ, **(env or {})},
                stdin=(
                    asyncio.subprocess.PIPE if stdin is not None else asyncio.subprocess.DEVNULL
                ),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
        except OSError as error:
            return ProcessResult(
                tuple(args),
                None,
                b"",
                f"{type(error).__name__}: {error}".encode(),
                (time.monotonic() - started) * 1000,
                launch_error=True,
            )
        assert process.stdout and process.stderr
        stdout_task = asyncio.create_task(self._read_bounded(process.stdout))
        stderr_task = asyncio.create_task(self._read_bounded(process.stderr))
        if stdin is not None:
            assert process.stdin
            process.stdin.write(stdin)
            await process.stdin.drain()
            process.stdin.close()
        timed_out = False
        cancelled = False
        try:
            await asyncio.wait_for(process.wait(), timeout)
        except TimeoutError:
            timed_out = True
            await self._terminate(process)
        except asyncio.CancelledError:
            cancelled = True
            await asyncio.shield(self._terminate(process))
        stdout, stdout_cut = await stdout_task
        stderr, stderr_cut = await stderr_task
        return ProcessResult(
            args=tuple(args),
            exit_code=process.returncode,
            stdout=stdout,
            stderr=stderr,
            duration_ms=(time.monotonic() - started) * 1000,
            timed_out=timed_out,
            cancelled=cancelled,
            truncated=stdout_cut or stderr_cut,
        )

    async def _read_bounded(
        self, stream: asyncio.StreamReader
    ) -> tuple[bytes, bool]:
        retained = bytearray()
        truncated = False
        while chunk := await stream.read(64 * 1024):
            remaining = self.output_limit_bytes - len(retained)
            if remaining > 0:
                retained.extend(chunk[:remaining])
            if len(chunk) > remaining:
                truncated = True
        if truncated:
            marker = b"\n[output truncated by controller]\n"
            if len(retained) + len(marker) <= self.output_limit_bytes:
                retained.extend(marker)
        return bytes(retained), truncated

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
        try:
            await asyncio.wait_for(process.wait(), self.kill_grace)
        except TimeoutError:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await process.wait()
