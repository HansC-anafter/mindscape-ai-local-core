"""Payload budget guards for hot task table JSON columns."""

from typing import Any, Dict, Optional

from backend.app.services.playbook_run_executor_core.result_compaction import (
    compact_workflow_result_for_task_context,
)
from backend.app.services.result_object_contract import (
    build_result_object_descriptor,
    json_payload_sha256,
    json_payload_size,
)


HOT_TASK_JSON_LIMIT_BYTES = 16 * 1024
HOT_TASK_JSON_WRITE_LIMIT_BYTES = 15 * 1024

DEFAULT_TASK_PAYLOAD_LIMITS = {
    "params": HOT_TASK_JSON_WRITE_LIMIT_BYTES,
    "result": HOT_TASK_JSON_WRITE_LIMIT_BYTES,
    "execution_context": HOT_TASK_JSON_WRITE_LIMIT_BYTES,
    "storyline_tags": HOT_TASK_JSON_WRITE_LIMIT_BYTES,
    "blocked_payload": HOT_TASK_JSON_WRITE_LIMIT_BYTES,
}

_CONTEXT_PRESERVE_KEYS = {
    "route_request",
    "runner_resource_requirements",
    "resource_requirements",
    "resource_admission",
    "host_resource_admission",
    "host_resource_decision",
    "host_resource_lane_id",
    "runtime_lane_id",
    "lane_id",
    "target_lane",
    "priority_class",
    "queue_partition",
    "queue_shard",
    "resource_class",
    "capability_code",
    "runner_profile_hint",
    "runtime_affinity",
    "runner_timeout_seconds",
    "concurrency_key",
    "concurrency",
    "execution_inputs_ref",
    "dependency_hold",
    "runner_skip_lock_key",
    "runner_skip_conflict_lock_key",
    "runner_skip_reason",
    "defer_until",
    "producer_kind",
    "visibility",
}

_CONTEXT_METADATA_KEYS = {
    "execution_id",
    "parent_execution_id",
    "playbook_code",
    "playbook_name",
    "status",
    "total_steps",
    "current_step_index",
    "workspace_id",
    "project_id",
    "profile_id",
    "thread_id",
    "meeting_session_id",
    "checkpoint",
    "sandbox_id",
    "execution_backend_hint",
    "execution_mode",
    "object_action_closure",
    "pending_reason",
    "pending_detail",
    "pending_since",
    "resume_after",
}

_CONTEXT_HEAVY_KEYS = {
    "workflow_result",
    "execution_trace",
    "browser_trace",
    "attachments",
    "files",
    "files_created",
    "files_modified",
    "screenshots",
    "logs",
    "stdout",
    "stderr",
    "raw_output",
    "raw_result",
}


class PayloadBudgetError(ValueError):
    """Raised when a hot-row payload cannot be safely stored."""


def _payload_descriptor(payload: Any, *, payload_kind: str) -> Dict[str, Any]:
    descriptor: Dict[str, Any] = {
        "_compacted": True,
        "payload_kind": payload_kind,
        "bytes": json_payload_size(payload),
        "checksum_sha256": json_payload_sha256(payload),
    }
    if isinstance(payload, dict):
        descriptor["keys"] = list(str(key) for key in list(payload.keys())[:20])
        descriptor["key_count"] = len(payload)
        status = payload.get("status")
        if status is not None:
            descriptor["status"] = _compact_scalar(status)
        error = payload.get("error")
        if error is not None:
            descriptor["error"] = _compact_scalar(error)
    elif isinstance(payload, list):
        descriptor["item_count"] = len(payload)
    return descriptor


def _compact_scalar(value: Any, *, max_string_chars: int = 500) -> Any:
    if isinstance(value, str) and len(value) > max_string_chars:
        return {
            "_type": "string",
            "chars": len(value),
            "preview": value[:max_string_chars],
            "_truncated": True,
        }
    return value


def _compact_metadata_value(
    value: Any,
    *,
    depth: int = 4,
    max_dict_keys: int = 40,
    max_list_preview: int = 10,
    max_string_chars: int = 500,
) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return _compact_scalar(value, max_string_chars=max_string_chars)
    if depth <= 0:
        return _payload_descriptor(value, payload_kind=type(value).__name__)
    if isinstance(value, list):
        compacted = [
            _compact_metadata_value(
                item,
                depth=depth - 1,
                max_dict_keys=max_dict_keys,
                max_list_preview=0,
                max_string_chars=max_string_chars,
            )
            for item in value[:max_list_preview]
        ]
        if len(value) > max_list_preview:
            compacted.append({"_truncated_count": len(value) - max_list_preview})
        return compacted
    if isinstance(value, dict):
        compacted: Dict[str, Any] = {}
        for index, (raw_key, raw_child) in enumerate(value.items()):
            if index >= max_dict_keys:
                compacted["_truncated_keys"] = len(value) - max_dict_keys
                break
            compacted[str(raw_key)] = _compact_metadata_value(
                raw_child,
                depth=depth - 1,
                max_dict_keys=max_dict_keys,
                max_list_preview=max_list_preview,
                max_string_chars=max_string_chars,
            )
        return compacted
    return _compact_scalar(str(value), max_string_chars=max_string_chars)


def _budget_metadata(
    *,
    field_name: str,
    original_bytes: int,
    limit_bytes: int,
) -> Dict[str, Any]:
    return {
        "field": field_name,
        "original_bytes": original_bytes,
        "limit_bytes": limit_bytes,
        "compacted": True,
    }


def _assert_within_budget(field_name: str, value: Any, *, limit_bytes: int) -> Any:
    size = json_payload_size(value)
    if size <= limit_bytes:
        return value
    raise PayloadBudgetError(
        f"{field_name} payload is {size} bytes; limit is {limit_bytes} bytes"
    )


def _compact_result_payload(value: Any, *, limit_bytes: int) -> Any:
    if not isinstance(value, dict):
        return _assert_within_budget("result", value, limit_bytes=limit_bytes)

    descriptor = build_result_object_descriptor(
        payload=value,
        summary=value.get("summary") or value.get("output") or value.get("status"),
        storage_ref=value.get("storage_ref"),
        execution_id=value.get("execution_id"),
        artifact_id=value.get("artifact_id"),
        landing_metadata=(
            value.get("landing") if isinstance(value.get("landing"), dict) else None
        ),
        deliverable_identity=value,
        acceptance_evidence=(
            value.get("acceptance_evidence")
            if isinstance(value.get("acceptance_evidence"), dict)
            else None
        ),
    )
    descriptor["_payload_budget"] = _budget_metadata(
        field_name="result",
        original_bytes=json_payload_size(value),
        limit_bytes=limit_bytes,
    )
    return _assert_within_budget("result", descriptor, limit_bytes=limit_bytes)


def _compact_execution_context(value: Any, *, limit_bytes: int) -> Any:
    if not isinstance(value, dict):
        return _assert_within_budget(
            "execution_context",
            value,
            limit_bytes=limit_bytes,
        )

    original_bytes = json_payload_size(value)
    compacted = dict(value)

    for key in list(_CONTEXT_HEAVY_KEYS):
        if key not in compacted:
            continue
        child = compacted[key]
        if key == "workflow_result" and isinstance(child, dict):
            compacted[key] = compact_workflow_result_for_task_context(
                child,
                max_bytes=min(64 * 1024, max(4096, limit_bytes // 4)),
            )
        else:
            compacted[key] = _payload_descriptor(child, payload_kind=key)

    size = json_payload_size(compacted)
    if size <= limit_bytes:
        if size == original_bytes:
            return value
        compacted["_payload_budget"] = _budget_metadata(
            field_name="execution_context",
            original_bytes=original_bytes,
            limit_bytes=limit_bytes,
        )
        return _assert_within_budget(
            "execution_context",
            compacted,
            limit_bytes=limit_bytes,
        )

    minimal: Dict[str, Any] = {
        "_payload_budget": _budget_metadata(
            field_name="execution_context",
            original_bytes=original_bytes,
            limit_bytes=limit_bytes,
        )
    }
    for key in list(_CONTEXT_PRESERVE_KEYS) + list(_CONTEXT_METADATA_KEYS):
        if key in value:
            minimal[key] = _compact_metadata_value(value[key])
    for key in _CONTEXT_HEAVY_KEYS:
        if key in value:
            child = value[key]
            if key == "workflow_result" and isinstance(child, dict):
                minimal[key] = compact_workflow_result_for_task_context(
                    child,
                    max_bytes=min(16 * 1024, max(2048, limit_bytes // 8)),
                )
            else:
                minimal[key] = _payload_descriptor(child, payload_kind=key)

    return _assert_within_budget(
        "execution_context",
        minimal,
        limit_bytes=limit_bytes,
    )


def _compact_blocked_payload(value: Any, *, limit_bytes: int) -> Any:
    if not isinstance(value, dict):
        return _assert_within_budget("blocked_payload", value, limit_bytes=limit_bytes)

    original_bytes = json_payload_size(value)
    compacted = _compact_metadata_value(
        value,
        depth=4,
        max_dict_keys=40,
        max_list_preview=10,
        max_string_chars=500,
    )
    if isinstance(compacted, dict):
        compacted["_payload_budget"] = _budget_metadata(
            field_name="blocked_payload",
            original_bytes=original_bytes,
            limit_bytes=limit_bytes,
        )
    return _assert_within_budget(
        "blocked_payload",
        compacted,
        limit_bytes=limit_bytes,
    )


def apply_task_payload_budget(
    field_name: str,
    value: Any,
    *,
    limit_bytes: Optional[int] = None,
) -> Any:
    """Return a payload that is safe for hot task JSON storage."""
    if value is None:
        return None

    normalized_field = str(field_name)
    limit = limit_bytes or DEFAULT_TASK_PAYLOAD_LIMITS.get(normalized_field)
    if limit is None:
        return value

    if json_payload_size(value) <= limit:
        return value

    if normalized_field == "result":
        return _compact_result_payload(value, limit_bytes=limit)
    if normalized_field == "execution_context":
        return _compact_execution_context(value, limit_bytes=limit)
    if normalized_field == "blocked_payload":
        return _compact_blocked_payload(value, limit_bytes=limit)

    return _assert_within_budget(normalized_field, value, limit_bytes=limit)
