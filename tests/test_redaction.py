from stack_integration.security import redact_text, redact_value


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
