#!/usr/bin/env python3
"""
Gemini CLI Runtime Bridge

Receives a task dispatch JSON payload on stdin, invokes `gemini` CLI,
and returns a structured JSON result on stdout.

This script is used as `GEMINI_CLI_RUNTIME_CMD` by TaskExecutor.

Protocol:
    stdin  -> JSON {execution_id, workspace_id, task, allowed_tools, max_duration, context}
    stdout <- JSON {status, output, error?, tool_calls?, files_modified?, files_created?}
"""

import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error

# Path to the Gemini CLI
GEMINI_CLI = os.environ.get(
    "GEMINI_CLI_PATH",
    "gemini",
)

# Maximum output to capture (characters)
MAX_OUTPUT = 100_000

# Backend URL injected from dispatch payload (set in main())
_bridge_backend_url = ""


def _fetch_auth_env():
    """Fetch auth env vars from backend /api/v1/auth/cli-token.

    Returns a dict of env vars to inject into subprocess, e.g.:
      {"GEMINI_API_KEY": "xxx"}
    or {"GOOGLE_GENAI_USE_VERTEXAI": "true", ...}

    Falls back to host env vars if the backend is unreachable.
    Raises SystemExit with clear message if auth is configured but broken.
    """
    api_url = _bridge_backend_url or os.environ.get("MINDSCAPE_BACKEND_API_URL", "")
    if not api_url:
        return _env_fallback()

    url = f"{api_url.rstrip('/')}/api/v1/auth/cli-token"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            env_vars = data.get("env", {})
            if env_vars:
                mode = data.get("auth_mode", "unknown")
                log(f"Auth env injected (mode={mode}, keys={list(env_vars.keys())})")
                return env_vars
            # Backend returned empty env -- check for auth error
            auth_mode = data.get("auth_mode", "unknown")
            error = data.get("error", "no env vars returned")
            log(f"Backend auth returned empty: mode={auth_mode}, error={error}")
            # Try host env fallback
            fallback = _env_fallback()
            if fallback:
                return fallback
            # No fallback available -- fail with clear message
            _fail_auth(auth_mode, error)
    except urllib.error.URLError as e:
        log(f"Failed to fetch auth env: {e}")
        return _env_fallback()
    except Exception as e:
        log(f"Auth env fetch error: {e}")
        return _env_fallback()


def _env_fallback():
    """Build auth env from host environment variables as fallback."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if api_key:
        log("Using GEMINI_API_KEY from host env (fallback)")
        return {"GEMINI_API_KEY": api_key}

    if os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() == "true":
        log("Using Vertex AI from host env (fallback)")
        return {
            "GOOGLE_GENAI_USE_VERTEXAI": "true",
            "GOOGLE_CLOUD_PROJECT": os.environ.get("GOOGLE_CLOUD_PROJECT", ""),
            "GOOGLE_CLOUD_LOCATION": os.environ.get(
                "GOOGLE_CLOUD_LOCATION", "us-central1"
            ),
        }

    gca_token = os.environ.get("GOOGLE_CLOUD_ACCESS_TOKEN", "")
    if os.environ.get("GOOGLE_GENAI_USE_GCA", "").lower() == "true" and gca_token:
        log("Using GCA from host env (fallback)")
        return {
            "GOOGLE_GENAI_USE_GCA": "true",
            "GOOGLE_CLOUD_ACCESS_TOKEN": gca_token,
        }

    log("WARNING: No auth configuration found (no API key, no Vertex AI, no GCA)")
    return {}


def _fail_auth(auth_mode: str, error: str):
    """Fail the task immediately with a clear auth error message."""
    if "expired" in error.lower() or "refresh failed" in error.lower():
        msg = (
            f"Authentication failed ({auth_mode}): {error}. "
            f"Please re-authenticate via Web Console > Settings > CLI Agent Keys > "
            f"Google Account tab > Disconnect then Connect."
        )
    elif "no oauth" in error.lower() or "no idp" in error.lower():
        msg = (
            f"Authentication not configured ({auth_mode}): {error}. "
            f"Please connect via Web Console > Settings > CLI Agent Keys."
        )
    else:
        msg = f"Authentication error ({auth_mode}): {error}"
    emit_result("failed", error=msg)
    sys.exit(1)


def _fetch_agent_context():
    """Fetch agent context (tables, role, guidance) from backend.

    Returns:
        Dict with role, tables, data_tool, data_guidance keys.
        Returns empty dict on failure.
    """
    api_url = _bridge_backend_url or os.environ.get("MINDSCAPE_BACKEND_API_URL", "")
    if not api_url:
        return {}
    url = f"{api_url.rstrip('/')}/api/v1/auth/agent-context"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read().decode())
    except Exception as e:
        log(f"Failed to fetch agent context: {e}")
        return {}


def _looks_like_auth_error(stderr_text: str) -> bool:
    """Detect auth-related errors in subprocess stderr."""
    if not stderr_text:
        return False
    lower = stderr_text.lower()
    auth_patterns = (
        "401",
        "403",
        "unauthenticated",
        "unauthorized",
        "token expired",
        "invalid credentials",
        "permission denied",
        "access denied",
        "auth not set",
    )
    return any(p in lower for p in auth_patterns)


def _extract_response(raw_stdout: str) -> tuple:
    """Extract the final response and error from Gemini CLI JSON output.

    When using --output-format json, the CLI returns:
        Success: {"session_id": "...", "response": "final answer", "stats": {...}}
        Error:   {"error": {"type": "...", "message": "...", "code": "..."}}

    Returns:
        (response_text, json_error_msg) - json_error_msg is None on success
    """
    if not raw_stdout:
        return (raw_stdout, None)
    try:
        parsed = json.loads(raw_stdout)
        # Check for error field
        error = parsed.get("error")
        error_msg = None
        if isinstance(error, dict):
            error_msg = error.get("message") or str(error)
        elif isinstance(error, str):
            error_msg = error

        response = parsed.get("response") or raw_stdout
        return (response, error_msg)
    except (json.JSONDecodeError, TypeError):
        return (raw_stdout, None)


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

    # Store backend URL from payload for token fetching
    global _bridge_backend_url
    _bridge_backend_url = payload.get("backend_api_url", "")

    if not task:
        emit_result("failed", error="Empty task")
        return

    # Build the prompt with dynamic system instruction
    agent_ctx = _fetch_agent_context()
    instruction_parts = []
    if agent_ctx.get("role"):
        instruction_parts.append(agent_ctx["role"])
    if agent_ctx.get("data_guidance"):
        instruction_parts.append(f"\nIMPORTANT: {agent_ctx['data_guidance']}")
    tables = agent_ctx.get("tables", [])
    if tables:
        table_lines = "\n".join(f"- {t}" for t in tables)
        instruction_parts.append(f"\nAvailable database tables:\n{table_lines}")

    system_instruction = "\n".join(instruction_parts) if instruction_parts else ""

    prompt_parts = []
    if system_instruction:
        prompt_parts.append(system_instruction)
    prompt_parts.append(task)

    # Inject execution metadata so the agent can ack/submit via MCP tools
    prompt_parts.append(
        f"\n\n[System Context] execution_id={execution_id}, "
        f"workspace_id={workspace_id}"
    )

    prompt = "\n".join(prompt_parts)

    # Determine working directory
    cwd = sandbox_path if sandbox_path and os.path.isdir(sandbox_path) else os.getcwd()

    # Build gemini CLI command with JSON output for structured response
    cmd = [
        GEMINI_CLI,
        "-p",
        prompt,
        "-o",
        "json",
    ]

    log(f"Executing: {' '.join(cmd[:3])}... (cwd={cwd})")

    # Build subprocess environment with auth injection
    sub_env = {**os.environ, "GEMINI_CLI_EXECUTION_ID": execution_id}

    # Fetch and inject auth env vars
    auth_env = _fetch_auth_env()
    sub_env.update(auth_env)

    # Server-side tool filtering: pass task hint to MCP gateway
    sub_env["MINDSCAPE_TASK_HINT"] = task[:500]

    start = time.monotonic()
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=max_duration,
            env=sub_env,
        )

        duration = time.monotonic() - start
        raw_stdout = (result.stdout or "")[:MAX_OUTPUT].strip()
        stdout, json_error = _extract_response(raw_stdout)
        stderr = (result.stderr or "")[:MAX_OUTPUT].strip()

        # Retry once with fresh auth on auth-related failure
        # Check both stderr AND stdout JSON error for auth indicators
        auth_in_stderr = _looks_like_auth_error(stderr)
        auth_in_json = _looks_like_auth_error(json_error or "")
        if result.returncode != 0 and (auth_in_stderr or auth_in_json):
            log("Auth error detected, retrying with fresh auth env")
            fresh_env = _fetch_auth_env()
            if fresh_env:
                sub_env.update(fresh_env)
                remaining = max_duration - duration
                if remaining > 10:
                    result = subprocess.run(
                        cmd,
                        cwd=cwd,
                        capture_output=True,
                        text=True,
                        timeout=int(remaining),
                        env=sub_env,
                    )
                    raw_stdout = (result.stdout or "")[:MAX_OUTPUT].strip()
                    stdout, json_error = _extract_response(raw_stdout)
                    stderr = (result.stderr or "")[:MAX_OUTPUT].strip()

        if result.returncode == 0:
            # Even on exit 0, check for JSON error (CLI may still report issues)
            if json_error:
                emit_result(
                    "completed",
                    output=stdout or json_error,
                )
            else:
                if not stdout:
                    log(
                        f"WARNING: empty response from CLI. raw_stdout={raw_stdout[:500]}"
                    )
                emit_result(
                    "completed",
                    output=stdout or raw_stdout or "(no response)",
                )
        else:
            # Build error message from both stderr and JSON error
            error_parts = []
            if json_error:
                error_parts.append(json_error)
            if stderr:
                error_parts.append(stderr[:500])
            error_msg = (
                " | ".join(error_parts)
                if error_parts
                else f"Exit code {result.returncode}"
            )
            emit_result(
                "failed",
                output=stdout,
                error=f"Exit code {result.returncode}: {error_msg}",
            )

    except subprocess.TimeoutExpired:
        emit_result("timeout", error=f"Timed out after {max_duration}s")
    except FileNotFoundError:
        emit_result(
            "failed",
            error=f"Gemini CLI not found at {GEMINI_CLI}",
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
