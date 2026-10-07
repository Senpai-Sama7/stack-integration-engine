import random
import time

from stack_integration.security import redact_text, redact_value
from stack_integration.security.redaction import PATTERNS


def test_common_secret_shapes_are_redacted():
    value = "Authorization: Bearer abc.def.ghi api_key=super-secret ghp_1234567890abcdef"
    redacted = redact_text(value)
    assert "abc.def.ghi" not in redacted
    assert "super-secret" not in redacted
    assert "ghp_1234567890abcdef" not in redacted
    assert redacted.count("[REDACTED]") == 3


def test_nested_values_are_redacted_without_mutating_numbers():
    assert redact_value({"message": "password=hunter2", "count": 2}) == {
        "message": "password=[REDACTED]",
        "count": 2,
    }


def test_real_world_credential_formats_are_redacted():
    secrets = [
        "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "sk-proj-AbCdEfGhIjKlMnOpQrStUvWx",
        "ghs_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "github_pat_11ABCDEFG0123456789_abcdefghijklmnop",
        "xoxb-1234567890-abcdefghij",
        "AKIAIOSFODNN7EXAMPLE",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U",
    ]
    for secret in secrets:
        assert secret not in redact_text(f"leaked {secret} here"), secret


def test_quoted_and_environment_style_secrets_are_redacted():
    text = (
        '{"api_key": "abc123def", "password": "hunter2"} '
        "GITHUB_TOKEN=ghtoken-value STACK_AGENT_GRANT=eyJ0.grant curl -H 'Bearer "
        "abcdefghijklmnopqrstuvwxyz'"
    )
    redacted = redact_text(text)
    for secret in [
        "abc123def",
        "hunter2",
        "ghtoken-value",
        "eyJ0.grant",
        "abcdefghijklmnopqrstuvwxyz",
    ]:
        assert secret not in redacted, secret
    assert "max_tokens=5" in redact_text("max_tokens=5")


def test_sensitive_structured_keys_are_redacted_but_counts_survive():
    value = redact_value(
        {"access_token": "opaque", "nested": {"client_secret": "x"}, "fencing_token": 3}
    )
    assert value == {
        "access_token": "[REDACTED]",
        "nested": {"client_secret": "[REDACTED]"},
        "fencing_token": 3,
    }


PEM_BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7\nabc123+/=\n"


def test_complete_truncated_and_oversized_private_keys_are_redacted():
    complete = f"before\n-----BEGIN PRIVATE KEY-----\n{PEM_BODY}-----END PRIVATE KEY-----\nafter"
    assert redact_text(complete) == "before\n[REDACTED]\nafter"

    two = (
        f"a -----BEGIN RSA PRIVATE KEY-----\n{PEM_BODY}-----END RSA PRIVATE KEY----- b "
        f"-----BEGIN EC PRIVATE KEY-----\n{PEM_BODY}-----END EC PRIVATE KEY----- c"
    )
    assert redact_text(two) == "a [REDACTED] b [REDACTED] c"

    truncated = f"output cut here\n-----BEGIN PRIVATE KEY-----\n{PEM_BODY}"
    cut = redact_text(truncated)
    assert "MIIEvQIB" not in cut and cut.startswith("output cut here\n[REDACTED]")

    # A body past the 20 KB cap is still redacted by the truncated-key rule.
    oversized = (
        "-----BEGIN PRIVATE KEY-----\n" + "QUJD" * 10_000 + "\n-----END PRIVATE KEY-----\ntail"
    )
    assert "QUJD" not in redact_text(oversized)
    assert redact_text(oversized).endswith("tail")

    # An unterminated marker no longer swallows a later, complete key's surroundings.
    mixed = (
        "-----BEGIN PRIVATE KEY-----\nnot a key.\nlater "
        f"-----BEGIN PRIVATE KEY-----\n{PEM_BODY}-----END PRIVATE KEY----- end"
    )
    assert redact_text(mixed).endswith("[REDACTED] end")


def test_hostile_output_cannot_stall_redaction():
    """Redaction runs on untrusted output on the controller's event loop. The previous
    unbounded `.*?` PEM pattern rescanned to the end of the text from every unterminated
    marker: this input took minutes. Linear matching finishes in well under a second."""
    flood = "-----BEGIN PRIVATE KEY-----\n" * 60_000
    start = time.perf_counter()
    redact_text(flood)
    assert time.perf_counter() - start < 10

    lone = "-----BEGIN PRIVATE KEY-----\n" + "a" * 3_000_000
    start = time.perf_counter()
    redact_text(lone)
    assert time.perf_counter() - start < 10


def test_clean_text_is_returned_unchanged_and_fast():
    text = "2026-10-07 INFO worker finished task t-1 in 41ms status=ok bytes=12044\n" * 40_000
    start = time.perf_counter()
    assert redact_text(text) is text or redact_text(text) == text
    assert time.perf_counter() - start < 5
    assert redact_text("") == ""


def test_trigger_prefilter_never_skips_a_matching_pattern():
    """The prefilter must be equivalent to applying every pattern unconditionally."""
    fragments = [
        "Authorization: Bearer abcdefghij.klmnop-qrstuv",
        "api_key=hunter2",
        '{"password": "p4ss"}',
        "GITHUB_TOKEN=ghtoken-value",
        "sk-ant-api03-AbCdEfGhIjKlMnOpQrStUv",
        "sk-proj-AbCdEfGhIjKlMnOpQrStUvWx",
        "ghs_AbCdEfGhIjKlMnOpQrStUvWxYz0123456789",
        "AKIAIOSFODNN7EXAMPLE",
        "xoxb-1234567890-abcdefghij",
        "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozjgNryP4J3jVmNHl0w5N",
        f"-----BEGIN PRIVATE KEY-----\n{PEM_BODY}-----END PRIVATE KEY-----",
        "-----BEGIN PRIVATE KEY-----\nQUJDRA==",
        "bearer abcdefghijklmnopqrstuvwx",
        "plain words and numbers 12345",
        "KEY TOKEN SECRET PASSWORD",
        "max_tokens=5",
        "\n",
        " ",
        "=",
        "_KEY=",
    ]
    rng = random.Random(20261007)
    for _ in range(400):
        text = "".join(rng.choice(fragments) + rng.choice([" ", "\n", "", ", "]) for _ in range(8))
        naive = text
        for pattern in PATTERNS:
            naive = pattern.sub(lambda m: (m.group(1) if m.lastindex else "") + "[REDACTED]", naive)
        assert redact_text(text) == naive, text
