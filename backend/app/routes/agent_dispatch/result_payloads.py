"""Helpers for preserving dispatch-time inputs through result landing."""

from typing import Any, Dict


_TRANSPORT_INPUT_KEYS = (
    "deliverable_id",
    "deliverable_name",
    "deliverable_path",
    "deliverable_targets",
)


def extract_dispatch_transport_inputs(payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        return {}
    context = payload.get("context")
    if not isinstance(context, dict):
        return {}

    merged: Dict[str, Any] = {}
    raw_inputs = context.get("inputs")
    if isinstance(raw_inputs, dict):
        merged.update(raw_inputs)

    for key in _TRANSPORT_INPUT_KEYS:
        value = context.get(key)
        if value is not None and key not in merged:
            merged[key] = value

    return merged


def merge_dispatch_transport_inputs(
    result_data: Dict[str, Any],
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    merged_result = dict(result_data or {})
    dispatch_inputs = extract_dispatch_transport_inputs(payload)
    if not dispatch_inputs:
        return merged_result

    context = dict(merged_result.get("context") or {})
    existing_inputs = context.get("inputs")
    if not isinstance(existing_inputs, dict):
        existing_inputs = {}

    merged_inputs = dict(dispatch_inputs)
    merged_inputs.update(existing_inputs)
    context["inputs"] = merged_inputs

    for key in _TRANSPORT_INPUT_KEYS:
        value = dispatch_inputs.get(key)
        if value is not None and key not in context:
            context[key] = value
        if value is not None and key not in merged_result:
            merged_result[key] = value

    if context:
        merged_result["context"] = context

    metadata = dict(merged_result.get("metadata") or {})
    existing_meta_inputs = metadata.get("inputs")
    if not isinstance(existing_meta_inputs, dict):
        existing_meta_inputs = {}
    merged_meta_inputs = dict(dispatch_inputs)
    merged_meta_inputs.update(existing_meta_inputs)
    metadata["inputs"] = merged_meta_inputs
    if metadata:
        merged_result["metadata"] = metadata

    return merged_result
