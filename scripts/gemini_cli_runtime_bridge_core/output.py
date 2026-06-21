import json
import sys


def emit_result(
    status: str,
    output: str = "",
    error: str | None = None,
    runtime_id: str | None = None,
    auth_scope: dict | None = None,
    tool_calls: list | None = None,
    files_modified: list | None = None,
    files_created: list | None = None,
) -> None:
    """Write JSON result to stdout."""
    result = {
        "status": status,
        "output": output,
        "tool_calls": tool_calls or [],
        "files_modified": files_modified or [],
        "files_created": files_created or [],
    }
    if error:
        result["error"] = error
    if runtime_id:
        result["runtime_id"] = runtime_id
    if auth_scope:
        result["auth_scope"] = auth_scope
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def log(msg: str) -> None:
    """Log to stderr (stdout is reserved for JSON output)."""
    print(f"[runtime_bridge] {msg}", file=sys.stderr)
