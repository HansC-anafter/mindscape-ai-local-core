"""
Helpers for merging transport-specific dispatch payload fields into results.

These helpers normalize result payloads so downstream landing and governance
logic can rely on a consistent shape even when some fields only exist on the
dispatch-side envelope.
"""

from __future__ import annotations

from typing import Any, Dict, List


def _merge_unique_items(primary: Any, fallback: Any) -> List[Any]:
    merged: List[Any] = []
    seen: set[str] = set()
    for source in (primary, fallback):
        if not isinstance(source, list):
            continue
        for item in source:
            marker = repr(item)
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(item)
    return merged


def merge_dispatch_transport_inputs(
    result: Dict[str, Any],
    dispatch_payload: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Merge dispatch-side transport context into a result payload.

    Result-side values always win. Dispatch fields are only used as fallback
    so downstream consumers can still see workspace/sandbox/thread context
    when the bridge result omitted them.
    """

    merged = dict(result or {})
    payload = dispatch_payload if isinstance(dispatch_payload, dict) else {}
    payload_context = payload.get("context") if isinstance(payload.get("context"), dict) else {}
    payload_metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}

    metadata = merged.get("metadata") if isinstance(merged.get("metadata"), dict) else {}
    merged_metadata = dict(payload_metadata)
    merged_metadata.update(metadata)

    fallback_context = {
        "workspace_id": payload.get("workspace_id"),
        "agent_id": payload.get("agent_id"),
        "requested_model": payload.get("model"),
        "project_id": payload_context.get("project_id"),
        "intent_id": payload_context.get("intent_id"),
        "lens_id": payload_context.get("lens_id"),
        "thread_id": payload_context.get("thread_id"),
        "auth_workspace_id": payload_context.get("auth_workspace_id"),
        "source_workspace_id": payload_context.get("source_workspace_id"),
        "sandbox_path": payload_context.get("sandbox_path"),
        "workspace_root": payload_context.get("sandbox_path"),
        "effective_sandbox_path": payload_context.get("sandbox_path"),
    }
    for key, value in fallback_context.items():
        if value is None or merged_metadata.get(key) not in (None, "", []):
            continue
        merged_metadata[key] = value
    merged["metadata"] = merged_metadata

    for key in ("attachments", "files_created", "files_modified", "tool_calls"):
        merged[key] = _merge_unique_items(merged.get(key), payload.get(key))

    if merged.get("output") in (None, "") and payload.get("task"):
        merged["output"] = ""

    return merged
