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
from typing import Dict, List, Tuple
import urllib.request
import urllib.error
import urllib.parse

# Path to the Gemini CLI
GEMINI_CLI = os.environ.get(
    "GEMINI_CLI_PATH",
    "gemini",
)

# Model to use for Gemini CLI execution
GEMINI_CLI_MODEL = os.environ.get("GEMINI_CLI_MODEL", "gemini-3-pro")

# Maximum output to capture (characters)
MAX_OUTPUT = 100_000

# Backend URL injected from dispatch payload (set in main())
_bridge_backend_url = ""


def _resolve_host_sandbox_path(sandbox_path: str, workspace_root: str) -> str:
    """Map container sandbox path (/app/...) to a host-accessible path."""
    if not sandbox_path:
        return ""
    if os.path.isdir(sandbox_path):
        return sandbox_path
    if not workspace_root or not sandbox_path.startswith("/app/"):
        return ""

    rel = sandbox_path[5:]
    candidate = os.path.join(workspace_root, rel)
    try:
        os.makedirs(candidate, exist_ok=True)
    except Exception as exc:
        log(f"Failed to create host sandbox {candidate}: {exc}")
        return ""
    return candidate if os.path.isdir(candidate) else ""


def _snapshot_files(root: str) -> Dict[str, Tuple[int, int]]:
    """Capture a lightweight recursive file snapshot for change detection."""
    if not root or not os.path.isdir(root):
        return {}

    snapshot: Dict[str, Tuple[int, int]] = {}
    skip_dirs = {".git", "__pycache__", "node_modules", ".pytest_cache"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [name for name in dirnames if name not in skip_dirs]
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            try:
                stat = os.stat(full_path)
            except OSError:
                continue
            rel_path = os.path.relpath(full_path, root)
            snapshot[rel_path] = (stat.st_mtime_ns, stat.st_size)
    return snapshot


def _diff_file_snapshots(
    before: Dict[str, Tuple[int, int]],
    after: Dict[str, Tuple[int, int]],
) -> Tuple[List[str], List[str]]:
    """Return created and modified relative paths between two snapshots."""
    created = sorted(path for path in after.keys() if path not in before)
    modified = sorted(
        path
        for path, after_meta in after.items()
        if path in before and before[path] != after_meta
    )
    return created, modified


def _fetch_auth_env(
    workspace_id: str = "",
    auth_workspace_id: str = "",
    source_workspace_id: str = "",
):
    """Fetch auth env vars, model, and runtime ID from backend.

    Returns a tuple of (env_vars, model, runtime_id, auth_trace):
      env_vars: dict of env vars to inject into subprocess
      model: agent CLI model from system settings (or None for default)
      runtime_id: selected runtime ID for quota attribution (or None)
      auth_trace: backend selection trace metadata

    Falls back to host env vars if the backend is unreachable.
    Raises SystemExit with clear message if auth is configured but broken.
    """
    api_url = _bridge_backend_url or os.environ.get("MINDSCAPE_BACKEND_API_URL", "")
    if not api_url:
        return _env_fallback(), None, None, {}

    params = {}
    if workspace_id:
        params["workspace_id"] = workspace_id
    if auth_workspace_id:
        params["auth_workspace_id"] = auth_workspace_id
    if source_workspace_id:
        params["source_workspace_id"] = source_workspace_id

    url = f"{api_url.rstrip('/')}/api/v1/auth/cli-token"
    if params:
        url = f"{url}?{urllib.parse.urlencode(params)}"
    try:
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
            env_vars = data.get("env", {})
            api_model = data.get("model") or None
            runtime_id = data.get("selected_runtime_id") or None
            if env_vars:
                mode = data.get("auth_mode", "unknown")
                selection_reason = data.get("selection_reason")
                log(
                    f"Auth env injected (mode={mode}, model={api_model}, "
                    f"runtime_id={runtime_id}, selection_reason={selection_reason}, "
                    f"keys={list(env_vars.keys())})"
                )
                return env_vars, api_model, runtime_id, data
            auth_mode = data.get("auth_mode", "unknown")
            error = data.get("error", "no env vars returned")
            log(f"Backend auth returned empty: mode={auth_mode}, error={error}")
            fallback = _env_fallback()
            if fallback:
                return fallback, api_model, runtime_id, data
            _fail_auth(auth_mode, error)
    except urllib.error.URLError as e:
        log(f"Failed to fetch auth env: {e}")
        return _env_fallback(), None, None, {}
    except Exception as e:
        log(f"Auth env fetch error: {e}")
        return _env_fallback(), None, None, {}


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


def _report_quota_exhausted(runtime_id):
    """Report quota exhaustion for the given runtime to the backend."""
    if not runtime_id:
        return
    api_url = _bridge_backend_url or os.environ.get("MINDSCAPE_BACKEND_API_URL", "")
    if not api_url:
        return
    url = f"{api_url.rstrip('/')}/api/v1/gca-pool/{runtime_id}/quota-exhausted"
    try:
        req = urllib.request.Request(url, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            log(f"Reported quota exhaustion for runtime {runtime_id}")
    except Exception as e:
        log(f"Failed to report quota exhaustion for {runtime_id}: {e}")


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


def _looks_like_quota_error(text: str) -> bool:
    """Detect quota/rate-limit errors (429 RESOURCE_EXHAUSTED)."""
    if not text:
        return False
    lower = text.lower()
    quota_patterns = (
        "429",
        "resource_exhausted",
        "resource exhausted",
        "quota exceeded",
        "rate limit",
        "too many requests",
    )
    return any(p in lower for p in quota_patterns)


def _extract_response(raw_stdout: str) -> tuple:
    """Extract the final response and error from Gemini CLI JSON output.

    When using --output-format json, the CLI returns:
        Success: {"session_id": "...", "response": "final answer", "stats": {...}}
        Error:   {"error": {"type": "...", "message": "...", "code": "..."}}

    When response is empty but tool calls succeeded, builds a summary
    from the stats instead of falling back to the raw JSON dump.

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

        response = parsed.get("response", "") or ""
        if response:
            return (response, error_msg)

        # response is empty -- check if tools were used successfully
        stats = parsed.get("stats", {})
        tool_stats = stats.get("tools", {})
        total_calls = tool_stats.get("totalCalls", 0)
        total_success = tool_stats.get("totalSuccess", 0)

        if total_calls > 0 and total_success > 0:
            # Build a structured summary from tool stats
            by_name = tool_stats.get("byName", {})
            tool_lines = []
            for name, info in by_name.items():
                calls = info.get("count", 0)
                ok = info.get("success", 0)
                fail = info.get("fail", 0)
                tool_lines.append(f"- {name}: {calls} calls ({ok} ok, {fail} fail)")
            summary_parts = [
                f"Agent completed {total_calls} tool call(s) "
                f"({total_success} succeeded) but did not produce "
                f"a final text response.",
            ]
            if tool_lines:
                summary_parts.append("Tool usage:")
                summary_parts.extend(tool_lines)
            summary_parts.append(
                "\nPlease re-run the query or ask a follow-up question "
                "to get a text summary of the results."
            )
            return ("\n".join(summary_parts), error_msg)

        # No tools called, truly empty response
        return ("", error_msg)
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
    auth_workspace_id = context.get("auth_workspace_id", "") or ""
    source_workspace_id = context.get("source_workspace_id", "") or ""
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
    table_schemas = agent_ctx.get("table_schemas", {})
    if table_schemas:
        # Format with full column schemas so model never guesses columns
        schema_lines = []
        for tname in sorted(table_schemas.keys()):
            cols = table_schemas[tname]
            schema_lines.append(f"- {tname}: {', '.join(cols)}")
        instruction_parts.append(
            f"\nAvailable database tables and columns:\n" + "\n".join(schema_lines)
        )
    elif tables:
        # Fallback: table names only (no schema available)
        table_lines = "\n".join(f"- {t}" for t in tables)
        instruction_parts.append(f"\nAvailable database tables:\n{table_lines}")

    # Inject pack-level agent guides
    pack_guides = agent_ctx.get("installed_pack_guides", [])
    if pack_guides:
        guide_lines = ["\n## Installed Capability Pack Guides"]
        for pg in pack_guides:
            guide_lines.append(
                f"### {pg.get('display_name', '')} ({pg.get('pack_code', '')})\n"
                f"{pg.get('guide', '')}"
            )
        instruction_parts.append("\n".join(guide_lines))

    system_instruction = "\n".join(instruction_parts) if instruction_parts else ""

    # Inject conversation context from dispatch payload (thread history,
    # active intents, current tasks, timeline activity)
    conversation_context = context.get("conversation_context", "")

    # Parse uploaded file metadata from dispatch payload (defensive schema)
    # Resolve container-relative paths to host-accessible paths via volume mount:
    #   Container: data/uploads/ws_id/file.mp4  (or /app/data/uploads/...)
    #   Host:      WORKSPACE_ROOT/data/uploads/ws_id/file.mp4
    uploaded_files = context.get("uploaded_files") or []
    uploaded_files_section = ""
    resolved_file_paths = []  # host-accessible file paths for CLI ingestion
    if uploaded_files:
        workspace_root = os.environ.get("MINDSCAPE_WORKSPACE_ROOT", "")
        print(
            f"[FileResolve] workspace_root={workspace_root}, uploaded_files={uploaded_files}",
            file=sys.stderr,
        )
        file_lines = []
        for f in uploaded_files:
            if isinstance(f, str):
                file_lines.append(f"- {f}")
                continue
            if not isinstance(f, dict):
                continue

            name = f.get("file_name", f.get("filename", f.get("file_id", "unknown")))
            ftype = f.get("file_type", f.get("mime_type", "unknown"))
            fpath = f.get("file_path", "")
            size = f.get("file_size", f.get("size_bytes", "?"))

            # Resolve container path → host path
            host_path = ""
            if fpath and workspace_root:
                # Strip leading /app/ if present (container CWD)
                rel = fpath
                if rel.startswith("/app/"):
                    rel = rel[5:]
                candidate = os.path.join(workspace_root, rel)
                if os.path.isfile(candidate):
                    host_path = candidate
                    file_stat = os.stat(candidate)
                    size = file_stat.st_size

            line = f"- {name} (type: {ftype}, size: {size})"
            if host_path:
                line += f"\n  Host path: {host_path}"
                if os.path.getsize(host_path) > 100:
                    resolved_file_paths.append(host_path)
            elif fpath:
                line += f"\n  Container path: {fpath} (not accessible from host)"
            file_lines.append(line)

        if file_lines:
            uploaded_files_section = "\n## Uploaded Files\n" + "\n".join(file_lines)
            if resolved_file_paths:
                uploaded_files_section += "\n\nYou can access these files directly at the host paths listed above."

    prompt_parts = []
    if system_instruction:
        prompt_parts.append(system_instruction)
    if conversation_context:
        prompt_parts.append(f"\n## Conversation Context\n{conversation_context}")
    if uploaded_files_section:
        prompt_parts.append(uploaded_files_section)
    prompt_parts.append(task)

    # Require a final text summary so the CLI always produces a response
    prompt_parts.append(
        "\n\nIMPORTANT: After using any tools, you MUST provide a final "
        "text summary of your findings. Never end your response with "
        "only tool calls and no text output."
    )

    # Inject execution metadata so the agent can ack/submit via MCP tools
    prompt_parts.append(
        f"\n\n[System Context] execution_id={execution_id}, "
        f"workspace_id={workspace_id}"
    )

    prompt = "\n".join(prompt_parts)

    workspace_root = os.environ.get("MINDSCAPE_WORKSPACE_ROOT", "")
    resolved_sandbox_path = _resolve_host_sandbox_path(sandbox_path, workspace_root)
    if resolved_sandbox_path:
        log(
            f"Resolved sandbox path {sandbox_path} -> {resolved_sandbox_path}"
        )

    # Determine working directory
    cwd = resolved_sandbox_path or os.getcwd()

    # Fetch auth env vars, model, and runtime ID from system settings
    auth_env, api_model, selected_runtime_id, auth_trace = _fetch_auth_env(
        workspace_id=workspace_id,
        auth_workspace_id=auth_workspace_id,
        source_workspace_id=source_workspace_id,
    )

    effective_model = api_model or GEMINI_CLI_MODEL

    # Build gemini CLI command with JSON output for structured response
    cmd = [
        GEMINI_CLI,
        "--model",
        effective_model,
        "--yolo",
        "-p",
        prompt,
        "-o",
        "json",
    ]

    log(f"Executing: {' '.join(cmd[:5])}... (model={effective_model}, cwd={cwd})")

    # Build subprocess environment with auth injection
    sub_env = {**os.environ, "GEMINI_CLI_EXECUTION_ID": execution_id}
    sub_env.update(auth_env)

    # Server-side tool filtering: enrich task hint with file context
    file_hint = context.get("file_hint", "")
    if file_hint:
        sub_env["MINDSCAPE_TASK_HINT"] = f"{task} {file_hint}"[:500]
    else:
        # Fallback: build hint from uploaded_files metadata
        hint_parts = [task]
        for f in context.get("uploaded_files") or []:
            if isinstance(f, dict):
                fname = f.get("file_name", "")
                ftype = f.get("detected_type") or f.get("file_type", "")
                if fname:
                    hint_parts.append(f"[{ftype}: {fname}]")
        sub_env["MINDSCAPE_TASK_HINT"] = " ".join(hint_parts)[:500]

    # Forward recommended packs as JSON for gateway
    rec_packs = context.get("recommended_pack_codes", [])
    if rec_packs:
        sub_env["MINDSCAPE_RECOMMENDED_PACKS"] = json.dumps(rec_packs)

    start = time.monotonic()
    before_files = _snapshot_files(cwd) if resolved_sandbox_path else {}
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
        after_files = _snapshot_files(cwd) if resolved_sandbox_path else {}
        files_created, files_modified = _diff_file_snapshots(
            before_files,
            after_files,
        )
        raw_stdout = (result.stdout or "")[:MAX_OUTPUT].strip()
        stdout, json_error = _extract_response(raw_stdout)
        stderr = (result.stderr or "")[:MAX_OUTPUT].strip()

        # Retry once with fresh auth on auth-related or quota failure
        # Check both stderr AND stdout JSON error for indicators
        auth_in_stderr = _looks_like_auth_error(stderr)
        auth_in_json = _looks_like_auth_error(json_error or "")
        quota_in_stderr = _looks_like_quota_error(stderr)
        quota_in_json = _looks_like_quota_error(json_error or "")
        is_retriable = (
            auth_in_stderr or auth_in_json or quota_in_stderr or quota_in_json
        )
        if result.returncode != 0 and is_retriable:
            is_quota = quota_in_stderr or quota_in_json
            error_kind = "quota" if is_quota else "auth"
            log(f"{error_kind} error detected, retrying with fresh auth env")
            if is_quota:
                _report_quota_exhausted(selected_runtime_id)
            fresh_env, _, selected_runtime_id, auth_trace = _fetch_auth_env(
                workspace_id=workspace_id,
                auth_workspace_id=auth_workspace_id,
                source_workspace_id=source_workspace_id,
            )
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
                    after_files = _snapshot_files(cwd) if resolved_sandbox_path else {}
                    files_created, files_modified = _diff_file_snapshots(
                        before_files,
                        after_files,
                    )
                    raw_stdout = (result.stdout or "")[:MAX_OUTPUT].strip()
                    stdout, json_error = _extract_response(raw_stdout)
                    stderr = (result.stderr or "")[:MAX_OUTPUT].strip()

        # Check for quota error after retry (both attempts exhausted)
        final_quota = _looks_like_quota_error(
            (result.stderr or "") + (json_error or "")
        )
        if result.returncode != 0 and final_quota:
            _report_quota_exhausted(selected_runtime_id)

        if result.returncode == 0:
            if json_error:
                emit_result(
                    "completed",
                    output=stdout or json_error,
                    runtime_id=selected_runtime_id,
                    auth_scope=_extract_auth_scope(auth_trace),
                    files_modified=files_modified,
                    files_created=files_created,
                )
            else:
                if not stdout:
                    log(
                        f"WARNING: empty response from CLI. raw_stdout={raw_stdout[:500]}"
                    )
                # _extract_response already handles tool-stats extraction,
                # so stdout should be a proper summary. If still empty,
                # prefer a clear fallback over dumping raw JSON.
                output = stdout or "(no response from agent)"
                emit_result(
                    "completed",
                    output=output,
                    runtime_id=selected_runtime_id,
                    auth_scope=_extract_auth_scope(auth_trace),
                    files_modified=files_modified,
                    files_created=files_created,
                )
        else:
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
                runtime_id=selected_runtime_id,
                auth_scope=_extract_auth_scope(auth_trace),
                files_modified=files_modified,
                files_created=files_created,
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


def _extract_auth_scope(auth_trace: dict | None) -> dict | None:
    """Return a compact auth-scope trace for backend persistence."""
    if not isinstance(auth_trace, dict):
        return None
    keys = (
        "requested_workspace_id",
        "effective_workspace_id",
        "auth_workspace_id",
        "source_workspace_id",
        "selection_reason",
        "selection_trace",
    )
    scope = {key: auth_trace.get(key) for key in keys if auth_trace.get(key) is not None}
    return scope or None


def emit_result(
    status: str,
    output: str = "",
    error: str = None,
    runtime_id: str = None,
    auth_scope: dict | None = None,
    tool_calls: list | None = None,
    files_modified: list | None = None,
    files_created: list | None = None,
):
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


def log(msg: str):
    """Log to stderr (stdout is reserved for JSON output)."""
    print(f"[runtime_bridge] {msg}", file=sys.stderr)


if __name__ == "__main__":
    main()
