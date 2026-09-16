import json

from stack_integration.providers.claude import ClaudeAdapter
from stack_integration.providers.process import ProcessResult


def test_claude_nested_usage_shape_is_preserved():
    payload = {
        "type": "result",
        "subtype": "success",
        "is_error": False,
        "session_id": "session",
        "result": "ok",
        "structured_output": {"ok": True},
        "usage": {
            "input_tokens": 2,
            "output_tokens_details": {"thinking_tokens": 37},
            "service_tier": "standard",
            "iterations": [{"input_tokens": 2}],
        },
    }
    process = ProcessResult(("claude",), 0, json.dumps(payload).encode(), b"", 1)
    result = ClaudeAdapter.parse_result(process)
    assert result.status == "completed"
    assert result.usage["output_tokens_details"] == {"thinking_tokens": 37}
