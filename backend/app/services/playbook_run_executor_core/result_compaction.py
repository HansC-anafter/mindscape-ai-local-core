"""Compact workflow results before storing them in hot task context."""

import json
from typing import Any, Dict


def _json_size(value: Any) -> int:
    try:
        return len(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return 0


def _compact_scalar(value: Any, *, max_string_chars: int) -> Any:
    if isinstance(value, str):
        if len(value) <= max_string_chars:
            return value
        return {
            "_type": "string",
            "chars": len(value),
            "preview": value[:max_string_chars],
            "_truncated": True,
        }
    return value


def _compact_value(
    value: Any,
    *,
    depth: int,
    max_dict_keys: int,
    max_list_preview: int,
    max_string_chars: int,
) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return _compact_scalar(value, max_string_chars=max_string_chars)

    if depth <= 0:
        if isinstance(value, dict):
            return {"_type": "object", "keys": len(value), "_compacted": True}
        if isinstance(value, list):
            return {"_type": "list", "count": len(value), "_compacted": True}
        return _compact_scalar(str(value), max_string_chars=max_string_chars)

    if isinstance(value, list):
        compacted = {
            "_type": "list",
            "count": len(value),
            "_compacted": True,
        }
        if value and max_list_preview > 0:
            compacted["preview"] = [
                _compact_value(
                    item,
                    depth=depth - 1,
                    max_dict_keys=max_dict_keys,
                    max_list_preview=0,
                    max_string_chars=max_string_chars,
                )
                for item in value[:max_list_preview]
            ]
        return compacted

    if isinstance(value, dict):
        compacted: Dict[str, Any] = {}
        for index, (raw_key, raw_child) in enumerate(value.items()):
            if index >= max_dict_keys:
                compacted["_truncated_keys"] = max(0, len(value) - max_dict_keys)
                break
            key = str(raw_key)
            compacted[key] = _compact_value(
                raw_child,
                depth=depth - 1,
                max_dict_keys=max_dict_keys,
                max_list_preview=max_list_preview,
                max_string_chars=max_string_chars,
            )
        return compacted

    return _compact_scalar(str(value), max_string_chars=max_string_chars)


def compact_workflow_result_for_task_context(
    workflow_result: Any,
    *,
    max_bytes: int = 64 * 1024,
) -> Any:
    """Return a small, UI-safe result summary for ``tasks.execution_context``.

    Full workflow payloads are landed separately. Keeping large arrays and nested
    step outputs in ``execution_context`` bloats the hot ``tasks`` table and turns
    queue/status reads into TOAST-heavy I/O.
    """

    if not isinstance(workflow_result, dict):
        return workflow_result

    compacted = _compact_value(
        workflow_result,
        depth=5,
        max_dict_keys=80,
        max_list_preview=2,
        max_string_chars=2048,
    )
    if isinstance(compacted, dict):
        compacted["_compacted"] = True
        compacted["_full_result_location"] = "artifact_result_json"

    if _json_size(compacted) <= max_bytes:
        return compacted

    compacted = _compact_value(
        workflow_result,
        depth=4,
        max_dict_keys=40,
        max_list_preview=1,
        max_string_chars=512,
    )
    if isinstance(compacted, dict):
        compacted["_compacted"] = True
        compacted["_full_result_location"] = "artifact_result_json"
        compacted["_original_bytes"] = _json_size(workflow_result)
    if _json_size(compacted) <= max_bytes:
        return compacted

    minimal: Dict[str, Any] = {
        "_compacted": True,
        "_full_result_location": "artifact_result_json",
        "_original_bytes": _json_size(workflow_result),
    }
    for key in ("status", "error", "execution_id"):
        value = workflow_result.get(key)
        if value is not None:
            minimal[key] = _compact_scalar(value, max_string_chars=512)
    return minimal
