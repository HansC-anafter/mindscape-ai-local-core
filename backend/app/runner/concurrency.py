"""Runner concurrency — lock key resolution and runner identity."""

import os
import socket
import uuid
from typing import Any, Dict, Optional


def _runner_id() -> str:
    val = (os.getenv("LOCAL_CORE_RUNNER_ID", "") or "").strip()
    if val:
        return val
    try:
        host = socket.gethostname()
    except Exception:
        host = "runner"
    return f"{host}-{uuid.uuid4().hex[:8]}"


def _is_ig_playbook(playbook_code: str) -> bool:
    """DEPRECATED: Legacy IG playbook detection. Retained for lock key fallback only."""
    code = (playbook_code or "").strip().lower()
    return code.startswith("ig_") or code.startswith("ig.")


def _resolve_lock_key(
    task_ctx: Optional[Dict[str, Any]],
    pack_id: str,
) -> Optional[str]:
    """Resolve the concurrency lock key for a task.

    Priority:
      1. Explicit: execution_context.concurrency.lock_key_input → read from inputs
      2. Legacy fallback: IG playbooks auto-lock by user_data_dir

    Returns a lock_key string (e.g. "concurrency:user_data_dir:/path/to/profile"),
    or None if the task has no concurrency constraint.
    """
    if not isinstance(task_ctx, dict):
        return None

    inputs = task_ctx.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}

    # --- Explicit concurrency policy (preferred) ---
    concurrency = task_ctx.get("concurrency")
    if isinstance(concurrency, dict):
        lock_key_input = concurrency.get("lock_key_input")
        lock_scope = concurrency.get("lock_scope", "input")
        if lock_key_input and lock_scope == "input":
            val = inputs.get(lock_key_input)
            if isinstance(val, str) and val.strip():
                return f"concurrency:{lock_key_input}:{val.strip()}"
        elif lock_scope == "playbook":
            return f"concurrency:playbook:{pack_id}"
        elif lock_scope == "workspace":
            ws = task_ctx.get("workspace_id", "")
            return f"concurrency:workspace:{ws}" if ws else None

    # --- Legacy fallback: IG playbooks lock by user_data_dir or pack_id ---
    if _is_ig_playbook(pack_id):
        val = inputs.get("user_data_dir")
        if isinstance(val, str) and val.strip():
            return f"ig_profile:{val.strip()}"
        # Browser-heavy IG playbooks without user_data_dir still need
        # concurrency protection to prevent multiple Chromium instances
        # from causing OOM.  Fall back to playbook-level lock.
        return f"concurrency:playbook:{pack_id}"

    return None


def _build_inputs(
    task_execution_id: str, task_ctx: Optional[Dict[str, Any]]
) -> Dict[str, Any]:
    ctx_inputs = None
    if isinstance(task_ctx, dict):
        ctx_inputs = task_ctx.get("inputs")
    inputs: Dict[str, Any] = dict(ctx_inputs) if isinstance(ctx_inputs, dict) else {}
    if "execution_id" not in inputs:
        inputs["execution_id"] = task_execution_id
    return inputs
