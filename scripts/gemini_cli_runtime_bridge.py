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

from gemini_cli_runtime_bridge_core import (
    GEMINI_CLI,
    GEMINI_CLI_MODEL,
    MAX_OUTPUT,
    emit_result,
    log,
    main,
    _diff_file_snapshots,
    _env_fallback,
    _extract_auth_scope,
    _extract_response,
    _fail_auth,
    _fetch_agent_context,
    _fetch_auth_env,
    _looks_like_auth_error,
    _looks_like_quota_error,
    _report_quota_exhausted,
    _resolve_host_sandbox_path,
    _snapshot_files,
)

__all__ = [
    "GEMINI_CLI",
    "GEMINI_CLI_MODEL",
    "MAX_OUTPUT",
    "emit_result",
    "log",
    "main",
    "_diff_file_snapshots",
    "_env_fallback",
    "_extract_auth_scope",
    "_extract_response",
    "_fail_auth",
    "_fetch_agent_context",
    "_fetch_auth_env",
    "_looks_like_auth_error",
    "_looks_like_quota_error",
    "_report_quota_exhausted",
    "_resolve_host_sandbox_path",
    "_snapshot_files",
]


if __name__ == "__main__":
    main()
