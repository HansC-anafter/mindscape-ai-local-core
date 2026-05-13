"""Descriptor contract for task result objects stored outside hot rows."""

import hashlib
import json
from typing import Any, Dict, List, Optional


RESULT_OBJECT_CONTRACT_SCHEMA_VERSION = 1
JSON_MIME_TYPE = "application/json"
DEFAULT_SUMMARY_LIMIT = 500
DEFAULT_METADATA_STRING_LIMIT = 500
DEFAULT_METADATA_LIST_LIMIT = 50


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
    except TypeError:
        return json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )


def json_payload_bytes(value: Any) -> bytes:
    """Return a deterministic JSON byte representation when possible."""
    return _json_dumps(value).encode("utf-8")


def json_payload_size(value: Any) -> int:
    """Return the serialized JSON byte size for a payload."""
    return len(json_payload_bytes(value))


def json_payload_sha256(value: Any) -> str:
    """Return the SHA-256 digest for a JSON payload."""
    return hashlib.sha256(json_payload_bytes(value)).hexdigest()


def _clean_string(value: Any) -> Optional[str]:
    if not isinstance(value, str):
        return None
    cleaned = value.strip()
    return cleaned or None


def _limit_text(value: Any, *, limit: int = DEFAULT_SUMMARY_LIMIT) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _extract_payload_summary(payload: Any) -> str:
    if not isinstance(payload, dict):
        return _limit_text(type(payload).__name__)

    for key in ("summary", "output", "message", "error", "status"):
        value = _clean_string(payload.get(key))
        if value:
            return _limit_text(value)

    steps = payload.get("steps")
    if isinstance(steps, dict) and steps:
        step_parts: List[str] = []
        for step_key, step_value in list(steps.items())[:5]:
            if isinstance(step_value, dict):
                status = _clean_string(step_value.get("status"))
                if status:
                    step_parts.append(f"{step_key}:{status}")
                    continue
            step_parts.append(str(step_key))
        if step_parts:
            return _limit_text(", ".join(step_parts))

    keys = ", ".join(str(key) for key in list(payload.keys())[:8])
    if keys:
        return _limit_text(f"object(keys={keys}, count={len(payload)})")
    return ""


def _bounded_metadata_value(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _limit_text(value, limit=DEFAULT_METADATA_STRING_LIMIT)
    if isinstance(value, list):
        bounded = [
            _bounded_metadata_value(item)
            for item in value[:DEFAULT_METADATA_LIST_LIMIT]
        ]
        if len(value) > DEFAULT_METADATA_LIST_LIMIT:
            bounded.append(
                {
                    "_truncated_count": len(value) - DEFAULT_METADATA_LIST_LIMIT,
                }
            )
        return bounded
    if isinstance(value, dict):
        bounded: Dict[str, Any] = {}
        for index, (raw_key, raw_child) in enumerate(value.items()):
            if index >= DEFAULT_METADATA_LIST_LIMIT:
                bounded["_truncated_keys"] = len(value) - DEFAULT_METADATA_LIST_LIMIT
                break
            bounded[str(raw_key)] = _bounded_metadata_value(raw_child)
        return bounded
    return _limit_text(value, limit=DEFAULT_METADATA_STRING_LIMIT)


def _bounded_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    strings: List[str] = []
    for item in value[:DEFAULT_METADATA_LIST_LIMIT]:
        cleaned = _clean_string(item)
        if cleaned:
            strings.append(cleaned)
    return strings


def _bounded_dict_list(value: Any) -> List[Dict[str, Any]]:
    if not isinstance(value, list):
        return []
    dicts: List[Dict[str, Any]] = []
    for item in value[:DEFAULT_METADATA_LIST_LIMIT]:
        if isinstance(item, dict):
            dicts.append(_bounded_metadata_value(item))
    return dicts


def build_result_object_descriptor(
    *,
    payload: Any,
    summary: Optional[str] = None,
    storage_ref: Optional[str] = None,
    execution_id: Optional[str] = None,
    artifact_id: Optional[str] = None,
    landing_metadata: Optional[Dict[str, Any]] = None,
    deliverable_identity: Optional[Dict[str, Any]] = None,
    acceptance_evidence: Optional[Dict[str, Any]] = None,
    payload_schema: str = "task_result",
) -> Dict[str, Any]:
    """Build the task.result descriptor for a landed result payload."""
    landing = _bounded_metadata_value(landing_metadata or {})
    deliverable = deliverable_identity or {}
    payload_summary = _clean_string(summary) or _extract_payload_summary(payload)
    result_json_path = (
        _clean_string(landing.get("result_json_path"))
        if isinstance(landing, dict)
        else None
    )
    object_key = _clean_string(storage_ref) or result_json_path

    descriptor: Dict[str, Any] = {
        "summary": _limit_text(payload_summary),
        "storage_ref": _clean_string(storage_ref),
        "execution_id": _clean_string(execution_id),
        "artifact_id": _clean_string(artifact_id),
        "result_object": {
            "schema_version": RESULT_OBJECT_CONTRACT_SCHEMA_VERSION,
            "object_key": object_key,
            "storage_ref": _clean_string(storage_ref),
            "checksum_sha256": json_payload_sha256(payload),
            "bytes": json_payload_size(payload),
            "mime_type": JSON_MIME_TYPE,
            "payload_schema": _clean_string(payload_schema) or "task_result",
        },
    }

    if result_json_path:
        descriptor["result_object"]["result_json_path"] = result_json_path
    if isinstance(landing, dict) and landing:
        descriptor["landing"] = landing

    deliverable_name = _clean_string(deliverable.get("deliverable_name"))
    deliverable_path = _clean_string(deliverable.get("deliverable_path"))
    if deliverable_name is not None:
        descriptor["deliverable_name"] = deliverable_name
    if deliverable_path is not None:
        descriptor["deliverable_path"] = deliverable_path

    deliverable_targets = _bounded_dict_list(deliverable.get("deliverable_targets"))
    if deliverable_targets:
        descriptor["deliverable_targets"] = deliverable_targets

    attachment_filenames = _bounded_string_list(deliverable.get("attachment_filenames"))
    if attachment_filenames:
        descriptor["attachment_filenames"] = attachment_filenames

    if acceptance_evidence:
        descriptor["acceptance_evidence"] = _bounded_metadata_value(acceptance_evidence)

    return descriptor
