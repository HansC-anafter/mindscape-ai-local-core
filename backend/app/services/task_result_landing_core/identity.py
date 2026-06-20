"""Deliverable identity helpers for task result landing."""

import os
from typing import Any, Dict, List, Optional

from app.services.task_result_landing_core.common import clean_string


def resolve_deliverable_identity(
    *,
    result_data: Dict[str, Any],
    result_json: Dict[str, Any],
    result_context: Dict[str, Any],
    result_metadata: Dict[str, Any],
    task: Optional[Any],
    attachment_filenames: List[str],
) -> Dict[str, Any]:
    """Resolve artifact title and deliverable identity from task/result payloads."""
    task_execution_context = getattr(task, "execution_context", None) or {}
    task_params = getattr(task, "params", None) or {}
    task_result = getattr(task, "result", None) or {}
    task_param_context = (
        task_params.get("context")
        if isinstance(task_params, dict)
        else {}
    ) or {}
    result_json_context = (
        result_json.get("context")
        if isinstance(result_json, dict)
        else {}
    ) or {}
    result_json_metadata = (
        result_json.get("metadata")
        if isinstance(result_json, dict)
        else {}
    ) or {}
    task_execution_inputs = (
        task_execution_context.get("inputs")
        if isinstance(task_execution_context, dict)
        else {}
    ) or {}
    task_input_params = (
        task_params.get("input_params")
        if isinstance(task_params, dict)
        else {}
    ) or {}
    result_context_inputs = (
        result_context.get("inputs")
        if isinstance(result_context, dict)
        else {}
    ) or {}
    result_metadata_inputs = (
        result_metadata.get("inputs")
        if isinstance(result_metadata, dict)
        else {}
    ) or {}
    result_json_context_inputs = (
        result_json_context.get("inputs")
        if isinstance(result_json_context, dict)
        else {}
    ) or {}
    result_json_metadata_inputs = (
        result_json_metadata.get("inputs")
        if isinstance(result_json_metadata, dict)
        else {}
    ) or {}

    candidate_mappings = [
        result_data,
        result_context,
        result_metadata,
        result_json,
        result_json_context,
        result_json_metadata,
        task_execution_context,
        task_execution_inputs,
        task_params,
        task_input_params,
        task_param_context,
        task_result,
        result_context_inputs,
        result_metadata_inputs,
        result_json_context_inputs,
        result_json_metadata_inputs,
    ]

    deliverable_path = None
    deliverable_name = None
    deliverable_targets = []
    for candidate in candidate_mappings:
        if not isinstance(candidate, dict):
            continue
        if deliverable_path is None:
            deliverable_path = clean_string(candidate.get("deliverable_path"))
        if deliverable_name is None:
            deliverable_name = clean_string(candidate.get("deliverable_name"))
        if not deliverable_targets:
            deliverable_targets = extract_deliverable_targets(candidate)
        if deliverable_path and deliverable_name:
            break

    if (deliverable_path is None or deliverable_name is None) and deliverable_targets:
        primary_target = deliverable_targets[0]
        if deliverable_path is None:
            deliverable_path = clean_string(primary_target.get("deliverable_path"))
        if deliverable_name is None:
            deliverable_name = clean_string(primary_target.get("deliverable_name"))

    artifact_title = None
    title_source = None
    if attachment_filenames:
        artifact_title = attachment_filenames[0]
        title_source = "attachment_filename"
    elif deliverable_path:
        artifact_title = os.path.basename(deliverable_path)
        title_source = "deliverable_path"
    elif deliverable_name:
        artifact_title = deliverable_name
        title_source = "deliverable_name"

    identity: Dict[str, Any] = {
        "artifact_title": artifact_title,
        "attachment_filenames": list(attachment_filenames or []),
    }
    if deliverable_name:
        identity["deliverable_name"] = deliverable_name
    if deliverable_path:
        identity["deliverable_path"] = deliverable_path
    if title_source:
        identity["title_source"] = title_source
    if deliverable_targets:
        identity["deliverable_targets"] = deliverable_targets
    return identity


def extract_deliverable_targets(candidate: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Normalize deliverable target metadata from a payload mapping."""
    raw_targets = candidate.get("deliverable_targets")
    if not isinstance(raw_targets, list):
        return []
    targets: List[Dict[str, Any]] = []
    for raw_target in raw_targets:
        if not isinstance(raw_target, dict):
            continue
        deliverable_id = clean_string(raw_target.get("deliverable_id"))
        deliverable_name = clean_string(raw_target.get("deliverable_name"))
        deliverable_path = clean_string(raw_target.get("deliverable_path"))
        normalized: Dict[str, Any] = {}
        if deliverable_id is not None:
            normalized["deliverable_id"] = deliverable_id
        if deliverable_name is not None:
            normalized["deliverable_name"] = deliverable_name
        if deliverable_path is not None:
            normalized["deliverable_path"] = deliverable_path
        if normalized:
            targets.append(normalized)
    return targets
