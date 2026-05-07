"""Runner concurrency: lock key resolution and runner identity."""

import os
import socket
import uuid
from typing import Any, Dict, Optional, List


def _runner_id() -> str:
    val = (os.getenv("LOCAL_CORE_RUNNER_ID", "") or "").strip()
    if val:
        return val
    try:
        host = socket.gethostname()
    except Exception:
        host = "runner"
    return f"{host}-{uuid.uuid4().hex[:8]}"


def _normalized_string(value: Any) -> Optional[str]:
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    if value is None or isinstance(value, (dict, list, tuple, set)):
        return None
    stripped = str(value).strip()
    return stripped or None


def _input_lock_value(
    inputs: Dict[str, Any],
    input_name: Optional[str],
    default_value: Any = None,
) -> Optional[str]:
    value = inputs.get(input_name) if input_name else None
    return _normalized_string(value) or _normalized_string(default_value)


def _render_lock_template(
    template: str,
    *,
    value: Optional[str],
    pack_id: str,
    playbook_code: str,
    workspace_id: Optional[str],
) -> Optional[str]:
    rendered = template
    replacements = {
        "value": value or "",
        "pack_id": pack_id or "",
        "playbook_code": playbook_code or "",
        "workspace_id": workspace_id or "",
    }
    for key, replacement in replacements.items():
        rendered = rendered.replace("{" + key + "}", replacement)
    return _normalized_string(rendered)


def _resolve_lock_from_policy(
    policy: Dict[str, Any],
    *,
    task_ctx: Dict[str, Any],
    inputs: Dict[str, Any],
    pack_id: str,
) -> Optional[str]:
    lock_scope = _normalized_string(policy.get("lock_scope")) or "input"
    lock_key_input = _normalized_string(policy.get("lock_key_input"))
    default_value = policy.get("default_lock_key_value")
    playbook_code = _normalized_string(task_ctx.get("playbook_code")) or pack_id
    workspace_id = _normalized_string(task_ctx.get("workspace_id")) or _normalized_string(
        inputs.get("workspace_id")
    )
    value = _input_lock_value(inputs, lock_key_input, default_value)

    template = _normalized_string(policy.get("lock_key_template"))
    if template:
        return _render_lock_template(
            template,
            value=value,
            pack_id=pack_id,
            playbook_code=playbook_code,
            workspace_id=workspace_id,
        )

    if lock_scope == "input" and lock_key_input and value:
        return f"concurrency:{lock_key_input}:{value}"
    if lock_scope == "playbook_input" and value:
        return f"concurrency:playbook_input:{pack_id}:{value}"
    if lock_scope == "playbook":
        return f"concurrency:playbook:{playbook_code}"
    if lock_scope == "workspace" and workspace_id:
        return f"concurrency:workspace:{workspace_id}"
    return None


def _resolve_lock_key(
    task_ctx: Optional[Dict[str, Any]],
    pack_id: str,
) -> Optional[str]:
    """Resolve the concurrency lock key for a task.

    Priority:
      1. Explicit: execution_context.concurrency.lock_key_input reads from inputs

    Returns a lock_key string (e.g. "concurrency:user_data_dir:/path/to/profile"),
    or None if the task has no concurrency constraint.
    """
    if not isinstance(task_ctx, dict):
        return None

    inputs = task_ctx.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}

    concurrency = task_ctx.get("concurrency")
    if isinstance(concurrency, dict):
        return _resolve_lock_from_policy(
            concurrency,
            task_ctx=task_ctx,
            inputs=inputs,
            pack_id=pack_id,
        )

    return None


def _resolve_lock_keys(
    task_ctx: Optional[Dict[str, Any]],
    pack_id: str,
) -> List[str]:
    """Resolve the primary concurrency key plus declared alias keys."""
    if not isinstance(task_ctx, dict):
        return []

    inputs = task_ctx.get("inputs")
    if not isinstance(inputs, dict):
        inputs = {}

    keys: list[str] = []
    primary = _resolve_lock_key(task_ctx, pack_id)
    if primary:
        keys.append(primary)

    concurrency = task_ctx.get("concurrency")
    lock_aliases = (
        concurrency.get("lock_aliases")
        if isinstance(concurrency, dict)
        else None
    )
    if isinstance(lock_aliases, list):
        for alias in lock_aliases:
            if not isinstance(alias, dict):
                continue
            alias_key = _resolve_lock_from_policy(
                alias,
                task_ctx=task_ctx,
                inputs=inputs,
                pack_id=pack_id,
            )
            if alias_key:
                keys.append(alias_key)

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
