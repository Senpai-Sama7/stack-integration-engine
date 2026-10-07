"""Provider interface and executable capability probes."""

from __future__ import annotations

import asyncio
import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from stack_integration.contracts.models import (
    Capability,
    CapabilityStatus,
    Provider,
    ProviderRequest,
    ProviderResult,
)
from stack_integration.providers.process import ProcessSupervisor

# Linux caps a single argv string at MAX_ARG_STRLEN (32 pages = 128 KiB). Review prompts
# embed candidate diffs, so larger prompts travel over stdin instead of failing with E2BIG.
ARGV_PROMPT_LIMIT_BYTES = 100 * 1024


def prompt_transport(prompt: str) -> tuple[str | None, bytes | None]:
    """Return ``(argv_prompt, stdin_bytes)``; exactly one is set."""
    encoded = prompt.encode()
    if len(encoded) <= ARGV_PROMPT_LIMIT_BYTES:
        return prompt, None
    return None, encoded


class ProviderAdapter(ABC):
    provider: Provider
    executable: str

    def __init__(self, executable: str, supervisor: ProcessSupervisor | None = None):
        self.executable = executable
        self.supervisor = supervisor or ProcessSupervisor()

    @abstractmethod
    async def probe(self) -> Capability: ...

    @abstractmethod
    async def execute(self, request: ProviderRequest) -> ProviderResult: ...


async def basic_probe(
    provider: Provider,
    executable: str,
    expected_help_tokens: dict[str, str],
    supervisor: ProcessSupervisor,
) -> Capability:
    resolved = shutil.which(executable)
    if resolved is None:
        return Capability(
            id=f"provider.{provider.value}",
            provider=provider,
            executable=executable,
            status=CapabilityStatus.UNSUPPORTED,
            detail="executable not found",
        )
    version_result, help_result = await asyncio.gather(
        supervisor.run([resolved, "--version"], cwd=Path.cwd(), timeout=15),
        supervisor.run([resolved, "--help"], cwd=Path.cwd(), timeout=15),
    )
    version = (version_result.stdout or version_result.stderr).decode(errors="replace").strip()
    help_text = (help_result.stdout + help_result.stderr).decode(errors="replace")
    features = {
        name: CapabilityStatus.SUPPORTED if token in help_text else CapabilityStatus.UNSUPPORTED
        for name, token in expected_help_tokens.items()
    }
    features_supported = all(status == CapabilityStatus.SUPPORTED for status in features.values())
    overall = (
        CapabilityStatus.SUPPORTED
        if version_result.exit_code == 0 and help_result.exit_code == 0 and features_supported
        else CapabilityStatus.DEGRADED
    )
    return Capability(
        id=f"provider.{provider.value}",
        provider=provider,
        executable=resolved,
        version=version,
        status=overall,
        features=features,
    )


async def probe_all(adapters: list[ProviderAdapter] | None = None) -> list[Capability]:
    if adapters is None:
        from stack_integration.providers.claude import ClaudeAdapter
        from stack_integration.providers.codex import CodexAdapter

        adapters = [CodexAdapter(), ClaudeAdapter()]
    return list(await asyncio.gather(*(adapter.probe() for adapter in adapters)))
