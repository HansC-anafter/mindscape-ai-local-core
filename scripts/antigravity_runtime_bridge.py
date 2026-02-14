#!/usr/bin/env python3
"""
Antigravity Runtime Bridge

Receives a task dispatch JSON payload on stdin, invokes `antigravity chat`
in agent mode, and returns a structured JSON result on stdout.

This script is used as `ANTIGRAVITY_IDE_RUNTIME_CMD` by TaskExecutor.

Protocol:
    stdin  → JSON {execution_id, workspace_id, task, allowed_tools, max_duration, context}
    stdout ← JSON {status, output, error?, tool_calls?, files_modified?, files_created?}
"""

import json
import os
import subprocess
import sys
import time

# Path to the Antigravity CLI
ANTIGRAVITY_CLI = os.environ.get(
    "ANTIGRAVITY_CLI_PATH",
    os.path.expanduser("~/.antigravity/antigravity/bin/antigravity"),
)

# Maximum output to capture (characters)
MAX_OUTPUT = 100_000


def main():
    # Read dispatch payload from stdin
    try:
        raw = sys.stdin.read()
        payload = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as e:
        emit_result("failed", error=f"Invalid JSON payload: {e}")
        return

    task = payload.get("task", "")
    execution_id = payload.get("execution_id", "unknown")
    workspace_id = payload.get("workspace_id", "")
    max_duration = payload.get("max_duration", 600)
    context = payload.get("context", {})
    sandbox_path = context.get("sandbox_path", "")

    if not task:
        emit_result("failed", error="Empty task")
        return

    # Build the prompt with execution context
    prompt_parts = [task]

    # Inject execution metadata so the agent can ack/submit via MCP tools
    prompt_parts.append(
        f"\n\n[System Context] execution_id={execution_id}, "
        f"workspace_id={workspace_id}"
    )

    prompt = "\n".join(prompt_parts)

    # Determine working directory
    cwd = sandbox_path if sandbox_path and os.path.isdir(sandbox_path) else os.getcwd()

    # Build antigravity chat command
    cmd = [
        ANTIGRAVITY_CLI,
        "chat",
        "-m",
        "agent",
        prompt,
    ]

    log(f"Executing: {' '.join(cmd[:4])}... (cwd={cwd})")

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=max_duration,
            env={**os.environ, "ANTIGRAVITY_EXECUTION_ID": execution_id},
        )

        duration = time.monotonic() - start
        stdout = (result.stdout or "")[:MAX_OUTPUT].strip()
        stderr = (result.stderr or "")[:MAX_OUTPUT].strip()

        if result.returncode == 0:
            emit_result(
                "completed",
                output=stdout or "Task completed successfully",
            )
        else:
            emit_result(
                "failed",
                output=stdout,
                error=f"Exit code {result.returncode}: {stderr[:500]}",
            )

    except subprocess.TimeoutExpired:
        emit_result("timeout", error=f"Timed out after {max_duration}s")
    except FileNotFoundError:
        emit_result(
            "failed",
            error=f"Antigravity CLI not found at {ANTIGRAVITY_CLI}",
        )
    except Exception as e:
        emit_result("failed", error=str(e))


def emit_result(status: str, output: str = "", error: str = None):
    """Write JSON result to stdout."""
    result = {"status": status, "output": output}
    if error:
        result["error"] = error
    json.dump(result, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


def log(msg: str):
    """Log to stderr (stdout is reserved for JSON output)."""
    print(f"[runtime_bridge] {msg}", file=sys.stderr)


if __name__ == "__main__":
    main()
