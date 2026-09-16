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
