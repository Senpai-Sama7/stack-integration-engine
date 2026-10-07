"""Bounded, cancellable subprocess supervision for providers and checks."""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

TRUNCATION_MARKER = b"\n[output truncated by controller]\n"
LINGERING_MARKER = (
    b"\n[controller: output pipes were still held open by a descendant after the command "
    b"exited; the process group was killed]\n"
)


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
    lingering_descendants: bool = False


@dataclass
class _Capture:
    limit: int
    data: bytearray = field(default_factory=bytearray)
    truncated: bool = False

    def extend(self, chunk: bytes) -> None:
        remaining = self.limit - len(self.data)
        if remaining > 0:
            self.data.extend(chunk[:remaining])
        if len(chunk) > remaining:
            self.truncated = True

    def finish(self, suffix: bytes = b"") -> bytes:
        if self.truncated and len(self.data) + len(TRUNCATION_MARKER) <= self.limit:
            self.data.extend(TRUNCATION_MARKER)
        return bytes(self.data) + suffix


class ProcessSupervisor:
    def __init__(
        self,
        *,
        output_limit_bytes: int = 10 * 1024 * 1024,
        kill_grace: float = 3.0,
        drain_timeout: float = 5.0,
    ):
        if output_limit_bytes < 1024:
            raise ValueError("output limit must be at least 1024 bytes")
        self.output_limit_bytes = output_limit_bytes
        self.kill_grace = kill_grace
        self.drain_timeout = drain_timeout

    async def run(
        self,
        args: list[str],
        *,
        cwd: str | Path,
        timeout: float,
        env: dict[str, str] | None = None,
        stdin: bytes | None = None,
        remove_env: Iterable[str] = (),
    ) -> ProcessResult:
        if not args:
            raise ValueError("process command cannot be empty")
        started = time.monotonic()
        environment = {**os.environ, **(env or {})}
        for name in remove_env:
            environment.pop(name, None)
        try:
            process = await asyncio.create_subprocess_exec(
                *args,
                cwd=str(cwd),
                env=environment,
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
        stdout = _Capture(self.output_limit_bytes)
        stderr = _Capture(self.output_limit_bytes)
        readers = {
            asyncio.create_task(self._read_bounded(process.stdout, stdout)),
            asyncio.create_task(self._read_bounded(process.stderr, stderr)),
        }
        # Feed stdin concurrently so a child that never reads it cannot block the
        # controller outside the wall-time limit once the pipe buffer fills.
        feeder = (
            asyncio.create_task(self._feed(process.stdin, stdin))
            if stdin is not None and process.stdin is not None
            else None
        )
        timed_out = False
        cancelled = False
        try:
            await asyncio.wait_for(self._wait_for_exit(process), timeout)
        except TimeoutError:
            timed_out = True
            await self._terminate(process)
        except asyncio.CancelledError:
            cancelled = True
            await asyncio.shield(self._terminate(process))
        if feeder is not None:
            feeder.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await feeder
        lingering = await self._drain(process, readers)
        return ProcessResult(
            args=tuple(args),
            exit_code=process.returncode,
            stdout=stdout.finish(),
            stderr=stderr.finish(LINGERING_MARKER if lingering else b""),
            duration_ms=(time.monotonic() - started) * 1000,
            timed_out=timed_out,
            cancelled=cancelled,
            truncated=stdout.truncated or stderr.truncated,
            lingering_descendants=lingering,
        )

    async def _drain(
        self, process: asyncio.subprocess.Process, readers: set[asyncio.Task[None]]
    ) -> bool:
        """Finish reading output without letting an escaped descendant hang the caller.

        A background child that inherited stdout/stderr keeps the pipes open after the
        command itself exits, so end-of-file may never arrive. Readers get a bounded
        grace period; after that the remaining process group is killed and reading stops.
        """
        _, pending = await asyncio.wait(readers, timeout=self.drain_timeout)
        if not pending:
            return False
        self._signal_group(process.pid, signal.SIGKILL)
        _, pending = await asyncio.wait(pending, timeout=1.0)
        for reader in pending:
            reader.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        return True

    @staticmethod
    async def _wait_for_exit(process: asyncio.subprocess.Process) -> None:
        """Return once the command itself exits.

        Before Python 3.13, ``Process.wait()`` resolves only after every pipe closes,
        so a descendant holding stdout open would make a finished command look hung.
        ``returncode`` is set as soon as the child watcher reaps the process.
        """
        waiter = asyncio.ensure_future(process.wait())
        try:
            while process.returncode is None and not waiter.done():
                await asyncio.wait({waiter}, timeout=0.05)
        finally:
            if not waiter.done():
                waiter.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await waiter

    @staticmethod
    async def _feed(writer: asyncio.StreamWriter, data: bytes) -> None:
        try:
            writer.write(data)
            await writer.drain()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with contextlib.suppress(Exception):
                writer.close()

    @staticmethod
    async def _read_bounded(stream: asyncio.StreamReader, capture: _Capture) -> None:
        # Keep reading past the limit so the child never blocks on a full pipe.
        while chunk := await stream.read(64 * 1024):
            capture.extend(chunk)

    @staticmethod
    def _signal_group(pid: int, signum: signal.Signals) -> None:
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signum)

    async def _terminate(self, process: asyncio.subprocess.Process) -> None:
        if process.returncode is None:
            self._signal_group(process.pid, signal.SIGTERM)
        try:
            await asyncio.wait_for(self._wait_for_exit(process), self.kill_grace)
        except TimeoutError:
            self._signal_group(process.pid, signal.SIGKILL)
            await self._wait_for_exit(process)
