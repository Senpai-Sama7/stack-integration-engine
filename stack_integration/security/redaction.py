"""Conservative redaction for controller logs, findings, messages, and reports.

Redaction runs on untrusted provider and test output, up to the supervisor's 10 MiB
per-stream limit, on the controller's event loop. Every pattern here is therefore
linear in the input: no unbounded repetition can be restarted at each of many start
positions, and a cheap substring check skips patterns whose literals cannot occur.
"""

from __future__ import annotations

import re
from typing import Any

REDACTED = "[REDACTED]"

# (pattern, lowercase literals of which at least one must appear for a match is possible).
# Case-sensitive patterns are checked against the lowercased text, so the check can only
# err toward running a pattern, never toward skipping one that would match.
_RULES: list[tuple[re.Pattern[str], tuple[str, ...]]] = [
    # Authorization headers, including Basic and token schemes.
    (
        re.compile(r"(?i)(authorization\s*[:=]\s*(?:bearer|basic|token)\s+)[A-Za-z0-9._~+/=-]+"),
        ("authorization",),
    ),
    # Bare bearer credentials outside a header (curl flags, logs).
    (re.compile(r"(?i)(\bbearer\s+)[A-Za-z0-9._~+/-]{16,}=*"), ("bearer",)),
    # key=value / key: value secrets, optionally quoted (JSON, YAML, env files, flags).
    (
        re.compile(
            r"(?i)((?:api[_-]?key|access[_-]?token|auth[_-]?token|refresh[_-]?token|"
            r"client[_-]?secret|secret[_-]?key|private[_-]?key|secret|password|passwd)"
            r"[\"']?\s*[=:]\s*[\"']?)[^\s,;\"'}]+"
        ),
        ("key", "token", "secret", "password", "passwd"),
    ),
    # Environment-style credentials such as GITHUB_TOKEN=... or STACK_AGENT_GRANT=...
    (
        re.compile(
            r"\b([A-Z][A-Z0-9_]*_(?:TOKEN|KEY|SECRET|PASSWORD|GRANT)\s*=\s*[\"']?)[^\s\"']+"
        ),
        ("_token", "_key", "_secret", "_password", "_grant"),
    ),
    # Well-known credential formats.
    (
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
        ("sk-", "sk_", "ghp_", "gho_", "ghu_", "ghs_", "ghr_", "github_pat_", "glpat-", "xox")
        + ("akia", "aiza"),
    ),
    # JSON Web Tokens.
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}"), ("eyj",)),
    # A complete PEM private key. The tempered body stops at the next BEGIN marker, so a
    # flood of unterminated markers costs one short scan each instead of one scan to the
    # end of the text each (which was quadratic), and the cap bounds a lone marker
    # followed by megabytes of text. Real bodies are a few KiB; longer ones fall through
    # to the truncated-key rule below, which redacts the whole base64 run.
    (
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
            r"(?:(?!-----BEGIN)[\s\S]){0,20000}?"
            r"-----END (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"
        ),
        ("private key",),
    ),
    # A truncated or oversized PEM private key (output cut off mid-key, only the header
    # printed, or a body past the cap above). Base64 bodies contain no '-', so the greedy
    # run ends at the next marker, the END footer, or the first non-base64 character.
    (
        re.compile(
            r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----[A-Za-z0-9+/=\s]*"
        ),
        ("private key",),
    ),
]

# Kept for callers that import the compiled patterns directly.
PATTERNS = [pattern for pattern, _ in _RULES]

# Structured values stored under these keys are redacted wholesale.
SENSITIVE_KEY = re.compile(
    r"(?i)(?:^|[_-])(?:password|passwd|secret|token|api[_-]?key|apikey|authorization|"
    r"credentials?|private[_-]?key)$"
)


def _replacement(match: re.Match[str]) -> str:
    return (match.group(1) if match.lastindex else "") + REDACTED


def redact_text(value: str) -> str:
    if not value:
        return value
    # Triggers are checked against the original text for every pattern. Earlier
    # substitutions only delete characters and insert "[REDACTED]", which contains no
    # trigger literal, so they cannot create a literal that the original lacked.
    lowered = value.lower()
    redacted = value
    for pattern, literals in _RULES:
        if any(literal in lowered for literal in literals):
            redacted = pattern.sub(_replacement, redacted)
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
