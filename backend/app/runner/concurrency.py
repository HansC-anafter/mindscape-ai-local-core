"""Runner concurrency — lock key resolution and runner identity."""

import os
import socket
import uuid
from typing import Any, Dict, Optional, List


_PLAYBOOK_INPUT_LOCK_PACKS = {
    "ig_analyze_following",
    "ig_batch_pin_references",
}

_LEGACY_PROFILE_ALIAS_PACKS = {
    "ig_analyze_following",
}


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


def _normalize_lock_scope(
    pack_id: str,
    lock_scope: Optional[str],
    lock_key_input: Optional[str],
) -> str:
    """Normalize concurrency scope for packs migrating to playbook-scoped profile locks."""
    normalized_scope = (lock_scope or "input").strip().lower()
    if (
        normalized_scope == "input"
        and lock_key_input == "user_data_dir"
        and pack_id in _PLAYBOOK_INPUT_LOCK_PACKS
    ):
        return "playbook_input"
    return normalized_scope


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
        lock_scope = _normalize_lock_scope(
            pack_id,
            concurrency.get("lock_scope", "input"),
            lock_key_input,
        )
        if lock_key_input and lock_scope in ("input", "playbook_input"):
            val = inputs.get(lock_key_input)
            if isinstance(val, str) and val.strip():
                if lock_scope == "playbook_input":
                    return (
                        f"concurrency:playbook_input:{pack_id}:{val.strip()}"
                    )
                return f"concurrency:{lock_key_input}:{val.strip()}"
        elif lock_scope == "playbook":
            return f"concurrency:playbook:{pack_id}"
        elif lock_scope == "workspace":
            ws = task_ctx.get("workspace_id", "")
            return f"concurrency:workspace:{ws}" if ws else None

    # --- Legacy fallback: IG playbooks lock by user_data_dir or playbook_code ---
    if _is_ig_playbook(pack_id):
        val = inputs.get("user_data_dir")
        if isinstance(val, str) and val.strip():
            return f"ig_profile:{val.strip()}"
        # Lock by playbook_code (e.g. ig_analyze_following, ig_analyze_reference)
        # so different task types can run concurrently.  Only same-playbook
        # tasks are serialized to prevent resource conflicts (e.g. multiple
        # Chromium instances or multiple MLX inferences).
        playbook_code = task_ctx.get("playbook_code") or pack_id
        return f"concurrency:playbook:{playbook_code}"

    return None


def _resolve_lock_keys(
    task_ctx: Optional[Dict[str, Any]],
    pack_id: str,
) -> List[str]:
    """Resolve the primary concurrency key plus backward-compatible aliases.

    During the IG lock migration, older tasks may still hold the legacy
    ``ig_profile:<user_data_dir>`` key while newer tasks may use either the
    explicit ``concurrency:user_data_dir:<user_data_dir>`` key or the
    playbook-scoped ``concurrency:playbook_input:<pack_id>:<user_data_dir>``
    key. Treat all of these as the same logical mutex during migration so
    same-profile runs cannot bypass each other.
    """
    primary = _resolve_lock_key(task_ctx, pack_id)
    if not primary:
        return []

    keys: list[str] = [primary]

    profile_ref: Optional[str] = None
    playbook_prefix = f"concurrency:playbook_input:{pack_id}:"
    if primary.startswith("concurrency:user_data_dir:"):
        profile_ref = primary[len("concurrency:user_data_dir:") :]
    elif primary.startswith("ig_profile:"):
        profile_ref = primary[len("ig_profile:") :]
    elif primary.startswith(playbook_prefix):
        profile_ref = primary[len(playbook_prefix) :]

    if profile_ref and pack_id in _LEGACY_PROFILE_ALIAS_PACKS:
        keys.append(f"concurrency:user_data_dir:{profile_ref}")
        keys.append(f"ig_profile:{profile_ref}")

    deduped: list[str] = []
    seen = set()
    for key in keys:
        if key and key not in seen:
            deduped.append(key)
            seen.add(key)
    return deduped


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
