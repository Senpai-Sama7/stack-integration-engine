"""Minimal MCP stdio server used to exercise the controller's MCP client."""

import json
import sys

TOOLS = [
    {"name": name, "inputSchema": {"type": "object"}}
    for name in (
        "nexus_workspace_overview",
        "nexus_context_pack",
        "nexus_impact_analysis",
        "nexus_write_file",
    )
]


def send(message):
    sys.stdout.write(json.dumps(message) + "\n")
    sys.stdout.flush()


for line in sys.stdin:
    request = json.loads(line)
    if "id" not in request:
        continue
    method = request["method"]
    params = request.get("params", {})
    if method == "initialize":
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"capabilities": {}}})
    elif method == "tools/list":
        # A notification first: the client must skip messages for other IDs.
        send({"jsonrpc": "2.0", "method": "notifications/progress", "params": {}})
        send({"jsonrpc": "2.0", "id": request["id"], "result": {"tools": TOOLS}})
    elif method == "tools/call":
        name = params.get("name")
        if name == "fail":
            send({"jsonrpc": "2.0", "id": request["id"], "error": {"code": -1, "message": "no"}})
        elif name == "malformed":
            sys.stdout.write("{not json\n")
            sys.stdout.flush()
        elif name == "exit":
            print("fatal: server stopping", file=sys.stderr, flush=True)
            sys.exit(3)
        elif name == "big":
            # A response far past asyncio's 64 KiB default line limit, and a stderr line
            # past the same limit with no newline-bounded shortcut.
            sys.stderr.write("e" * 300_000 + "\n")
            sys.stderr.flush()
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "result": {"content": [{"type": "text", "text": "x" * 300_000}]},
                }
            )
        elif name == "not_object":
            send({"jsonrpc": "2.0", "id": request["id"], "result": [1, 2]})
        else:
            text = json.dumps({"tool": name, "arguments": params.get("arguments")})
            send(
                {
                    "jsonrpc": "2.0",
                    "id": request["id"],
                    "result": {"content": [{"type": "text", "text": text}]},
                }
            )
