"""Conservative redaction for controller logs, findings, messages, and reports."""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

PATTERNS = [
    # Authorization headers, including Basic and token schemes.
    re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=-]+"),
    # Bare bearer credentials outside a header (curl flags, logs).
    re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]{16,}=*"),
    # key=value / key: value secrets, optionally quoted (JSON, YAML, env files, flags).
    re.compile(
        r"(?i)((?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|"
        r"client[_-]?secret|secret[_-]?key|private[_-]?key|secret|password|passwd)"
        r"[\"']?\s*[=:]\s*[\"']?)[^\s,;\"'}]+"
    ),
    # Environment-style credentials such as GITHUB_TOKEN=... or STACK_AGENT_GRANT=...
    re.compile(r"\b([A-Z][A-Z0-9_]*_(?:TOKEN|KEY|SECRET|PASSWORD|GRANT)\s*=\s*[\"']?)[^\s\"']+"),
    # Well-known credential formats.
    re.compile(
        r"\b(?:"
        r"sk-ant-[A-Za-z0-9_-]{8,}"  # Anthropic
        r"|sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}"  # OpenAI
        r"|sk_(?:live|test)_[A-Za-z0-9]{16,}"  # Stripe
        r"|sk_[A-Za-z0-9_-]{12,}"
        r"|gh[pousr]_[A-Za-z0-9]{12,}"  # GitHub
        r"|github_pat_[A-Za-z0-9_]{12,}"
        r"|glpat-[A-Za-z0-9_-]{20,}"  # GitLab
        r"|xox[abprs]-[A-Za-z0-9-]{10,}"  # Slack
        r"|AKIA[0-9A-Z]{16}"  # AWS access key ID
        r"|AIza[0-9A-Za-z_-]{35}"  # Google API key
        r")"
    ),
    # JSON Web Tokens.
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"),
    re.compile(
        r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----.*?"
        r"-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----",
        re.DOTALL,
    ),
]

# Structured values stored under these keys are redacted wholesale.
SENSITIVE_KEY = re.compile(
    r"(?i)(?:^|[_-])(?:password|passwd|secret|token|api[_-]?key|apikey|authorization|"
    r"credentials?|private[_-]?key)$"
)


def redact_text(value: str) -> str:
    redacted = value
    for pattern in PATTERNS:
        redacted = pattern.sub(
            lambda match: (match.group(1) if match.lastindex else "") + REDACTED,
            redacted,
        )
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_value(item) for item in value)
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if isinstance(key, str) and isinstance(item, str) and SENSITIVE_KEY.search(key)
                else redact_value(item)
            )
            for key, item in value.items()
        }
    return value
