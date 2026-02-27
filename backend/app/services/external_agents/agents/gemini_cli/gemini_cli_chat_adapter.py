#!/usr/bin/env python3
"""
Gemini CLI Chat Adapter — bridge between TaskExecutor JSON protocol
and the `gemini` CLI.

Protocol (as expected by task_executor._execute_via_ide_runtime):
  stdin:  JSON payload with execution_id, workspace_id, task, etc.
  stdout: JSON result with status, output, error, tool_calls, files_modified, etc.
  exit 0 on success, non-zero on failure.

Usage:
  export GEMINI_CLI_RUNTIME_CMD="python3 /path/to/gemini_cli_chat_adapter.py"
  # Then task_executor will pipe JSON payloads to this script.

Requirements:
  - Gemini CLI must be installed.
  - `gemini` CLI must be in PATH (or GEMINI_CLI_PATH set).
"""

import json
import os
import subprocess
import sys


GEMINI_CLI = os.environ.get(
    "GEMINI_CLI_PATH",
    "gemini",
)


def main():
    # Read JSON payload from stdin
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw)
    except (json.JSONDecodeError, Exception) as e:
        emit_result(status="failed", error=f"Invalid JSON input: {e}")
        sys.exit(1)

    task = payload.get("task", "").strip()
    execution_id = payload.get("execution_id", "")
    workspace_id = payload.get("workspace_id", "")

    if not task:
        emit_result(
            status="failed",
            error="Empty task in payload",
            execution_id=execution_id,
        )
        sys.exit(1)

    # Verify gemini CLI exists
    if not os.path.isfile(GEMINI_CLI):
        emit_result(
            status="failed",
            error=f"Gemini CLI not found at {GEMINI_CLI}",
            execution_id=execution_id,
        )
        sys.exit(1)

    # Build command
    cmd = [
        GEMINI_CLI,
        "-p",
        task,
    ]

    # Add context files if provided
    context = payload.get("context", {})
    sandbox_path = context.get("sandbox_path", "")
    cwd = sandbox_path if sandbox_path and os.path.isdir(sandbox_path) else os.getcwd()

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=payload.get("max_duration", 600),
            cwd=cwd,
        )
    except subprocess.TimeoutExpired:
        emit_result(
            status="timeout",
            error=f"gemini CLI timed out after {payload.get('max_duration', 600)}s",
            execution_id=execution_id,
        )
        sys.exit(1)
    except FileNotFoundError:
        emit_result(
            status="failed",
            error=f"gemini CLI not executable: {GEMINI_CLI}",
            execution_id=execution_id,
        )
        sys.exit(1)

    stdout = proc.stdout.strip()
    stderr = proc.stderr.strip()

    if proc.returncode != 0:
        emit_result(
            status="failed",
            output=stdout,
            error=f"gemini CLI exit code {proc.returncode}: {stderr[:500]}",
            execution_id=execution_id,
        )
        sys.exit(0)  # exit 0 so task_executor reads our JSON, not its own error

    # Try to parse structured JSON from gemini CLI output
    try:
        result_data = json.loads(stdout) if stdout else {}
        # If gemini returned structured data, pass it through
        result_data.setdefault("status", "completed")
        result_data.setdefault("execution_id", execution_id)
        result_data["metadata"] = {
            "executor_location": "ide",
            "runtime": "gemini_cli",
            "workspace_id": workspace_id,
        }
        json.dump(result_data, sys.stdout)
    except json.JSONDecodeError:
        # Plain text output — wrap it
        emit_result(
            status="completed",
            output=stdout,
            execution_id=execution_id,
            workspace_id=workspace_id,
        )


def emit_result(
    status="completed",
    output="",
    error=None,
    execution_id="",
    workspace_id="",
    tool_calls=None,
    files_modified=None,
    files_created=None,
):
    """Write JSON result to stdout."""
    result = {
        "status": status,
        "output": output,
        "error": error,
        "execution_id": execution_id,
        "tool_calls": tool_calls or [],
        "files_modified": files_modified or [],
        "files_created": files_created or [],
        "metadata": {
            "executor_location": "ide",
            "runtime": "gemini_cli",
            "workspace_id": workspace_id,
        },
    }
    json.dump(result, sys.stdout)


if __name__ == "__main__":
    main()
