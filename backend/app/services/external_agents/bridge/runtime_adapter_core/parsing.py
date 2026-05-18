"""Dispatch response parsing helpers."""

import time
from typing import Any, Dict

from backend.app.services.external_agents.core.base_adapter import RuntimeExecResponse


def parse_dispatch_response(
    raw: Dict[str, Any],
    start_time: float,
) -> RuntimeExecResponse:
    """Parse a transport-agnostic dispatch response into RuntimeExecResponse."""
    status = raw.get("status", "failed")
    duration = raw.get("duration_seconds", time.monotonic() - start_time)
    dispatch_metadata = raw.get("metadata", {})
    if not isinstance(dispatch_metadata, dict):
        dispatch_metadata = {}
    agent_metadata = {
        "transport": dispatch_metadata.get("transport", "unknown"),
        "execution_id": raw.get("execution_id", ""),
        "governance": raw.get("governance", {}),
        "dispatch_metadata": dispatch_metadata,
    }
    if "codex_account_identity" in dispatch_metadata:
        agent_metadata["codex_account_identity"] = dispatch_metadata.get(
            "codex_account_identity"
        )

    return RuntimeExecResponse(
        success=status in ("completed", "dispatched_to_ide"),
        output=raw.get("output", ""),
        duration_seconds=duration,
        tool_calls=raw.get("tool_calls", []),
        files_modified=raw.get("files_modified", []),
        files_created=raw.get("files_created", []),
        error=raw.get("error"),
        exit_code=0 if status in ("completed", "dispatched_to_ide") else 1,
        agent_metadata=agent_metadata,
    )
