"""Metadata and evidence helpers for task result landing."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from app.services.task_result_landing_core.common import clean_string
from backend.app.services.result_object_contract import (
    build_result_object_descriptor,
    json_payload_size,
)


def build_landing_metadata(
    *,
    artifact_dir: str,
    result_json_path: str,
    summary_md_path: str,
    attachments: List[str],
    attachment_filenames: List[str],
    landed_at: datetime,
) -> Dict[str, Any]:
    """Build normalized landing metadata for artifact and task payloads."""
    if (
        not artifact_dir
        and not result_json_path
        and not summary_md_path
        and not attachments
        and not attachment_filenames
    ):
        return {}
    metadata = {
        "artifact_dir": artifact_dir or None,
        "result_json_path": result_json_path or None,
        "summary_md_path": summary_md_path or None,
        "attachments": list(attachments or []),
        "attachments_count": len(attachments or []),
        "landed_at": landed_at.isoformat(),
    }
    if attachment_filenames:
        metadata["attachment_filenames"] = list(attachment_filenames)
    return metadata


def merge_artifact_metadata(
    *,
    existing_metadata: Optional[Dict[str, Any]],
    project_id: Optional[str],
    has_attachments: bool,
    landing_metadata: Dict[str, Any],
    deliverable_identity: Dict[str, Any],
    acceptance_evidence: Dict[str, Any],
) -> Dict[str, Any]:
    """Merge landing metadata into the existing artifact metadata shape."""
    metadata = dict(existing_metadata or {})
    metadata["source"] = metadata.get("source") or "task_runner"
    if project_id is not None:
        metadata["project_id"] = project_id
    metadata["has_attachments"] = has_attachments or bool(metadata.get("has_attachments"))
    if landing_metadata:
        metadata["landing"] = landing_metadata
    deliverable_name = clean_string(deliverable_identity.get("deliverable_name"))
    deliverable_path = clean_string(deliverable_identity.get("deliverable_path"))
    title_source = clean_string(deliverable_identity.get("title_source"))
    attachment_filenames = deliverable_identity.get("attachment_filenames")
    deliverable_targets = deliverable_identity.get("deliverable_targets")
    if deliverable_name is not None:
        metadata["deliverable_name"] = deliverable_name
    if deliverable_path is not None:
        metadata["deliverable_path"] = deliverable_path
    if title_source is not None:
        metadata["deliverable_title_source"] = title_source
    if isinstance(deliverable_targets, list) and deliverable_targets:
        metadata["deliverable_targets"] = list(deliverable_targets)
    if isinstance(attachment_filenames, list) and attachment_filenames:
        metadata["attachment_filenames"] = list(attachment_filenames)
    if acceptance_evidence:
        metadata["acceptance_evidence"] = dict(acceptance_evidence)
    return metadata


def build_artifact_content_descriptor(
    result_descriptor: Dict[str, Any],
) -> Dict[str, Any]:
    """Build bounded artifact content from the full result descriptor."""
    return {
        "summary": result_descriptor.get("summary"),
        "storage_ref": result_descriptor.get("storage_ref"),
        "execution_id": result_descriptor.get("execution_id"),
        "artifact_id": result_descriptor.get("artifact_id"),
        "result_object": dict(result_descriptor.get("result_object") or {}),
    }


def build_task_result_payload(
    *,
    existing_result: Dict[str, Any],
    incoming_result: Dict[str, Any],
    summary: str,
    storage_ref: Optional[str],
    execution_id: str,
    artifact_id: Optional[str],
    landing_metadata: Dict[str, Any],
    deliverable_identity: Dict[str, Any],
    acceptance_evidence: Dict[str, Any],
    pd_storyboard_evidence: Optional[Dict[str, Any]] = None,
    object_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Build the task result payload while dropping oversized runtime traces."""
    preserved_existing: Dict[str, Any] = {}
    if isinstance(existing_result, dict):
        reserved_keys = {
            "summary",
            "storage_ref",
            "execution_id",
            "artifact_id",
            "result_object",
            "landing",
            "deliverable_name",
            "deliverable_path",
            "deliverable_targets",
            "attachment_filenames",
            "acceptance_evidence",
            "pd_storyboard_evidence",
        }
        heavy_keys = {
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
        for key, value in existing_result.items():
            if key in reserved_keys or key in heavy_keys or value is None:
                continue
            if json_payload_size(value) <= 8 * 1024:
                preserved_existing[key] = value

    result_payload = build_result_object_descriptor(
        payload=incoming_result,
        summary=summary,
        storage_ref=storage_ref,
        object_key=object_key,
        execution_id=execution_id,
        artifact_id=artifact_id,
        landing_metadata=landing_metadata,
        deliverable_identity=deliverable_identity,
        acceptance_evidence=acceptance_evidence,
    )
    if pd_storyboard_evidence:
        result_payload["pd_storyboard_evidence"] = dict(pd_storyboard_evidence)
    result_payload.update(preserved_existing)
    return result_payload


def resolve_nested_value(data: Dict[str, Any], path: str) -> Any:
    """Resolve a dotted path from a nested dictionary."""
    if not isinstance(data, dict) or not isinstance(path, str) or not path:
        return None
    current: Any = data
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return None
    return current


def has_material_value(value: Any) -> bool:
    """Return True when a value is meaningful evidence."""
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) > 0
    return True


def first_nested_value(roots: List[Dict[str, Any]], paths: List[str]) -> Any:
    """Return the first material value found across roots and dotted paths."""
    for root in roots:
        if not isinstance(root, dict):
            continue
        for path in paths:
            value = resolve_nested_value(root, path)
            if has_material_value(value):
                return value
    return None


def extract_storyboard_preview_evidence(
    candidate: Dict[str, Any],
    *,
    task_pack_id: str,
) -> Dict[str, Any]:
    """Extract storyboard preview acceptance evidence from a result candidate."""
    if not isinstance(candidate, dict):
        return {}

    storyboard = candidate.get("storyboard")
    if not isinstance(storyboard, dict):
        return {}

    storyboard_id = clean_string(storyboard.get("storyboard_id"))
    session_id = clean_string(candidate.get("session_id"))
    if not storyboard_id and not session_id:
        return {}

    evidence: Dict[str, Any] = {"evidence_kind": "storyboard_preview"}
    if task_pack_id:
        evidence["playbook_code"] = task_pack_id
    if session_id:
        evidence["session_id"] = session_id

    storyboard_evidence: Dict[str, Any] = {}
    if storyboard_id:
        storyboard_evidence["storyboard_id"] = storyboard_id
        evidence["storyboard_id"] = storyboard_id
    workspace_id = clean_string(storyboard.get("workspace_id"))
    if workspace_id:
        storyboard_evidence["workspace_id"] = workspace_id
    scenes = storyboard.get("scenes")
    if isinstance(scenes, list):
        storyboard_evidence["scene_count"] = len(scenes)
    if storyboard_evidence:
        evidence["storyboard"] = storyboard_evidence

    for key in (
        "source_type",
        "run_id",
        "status",
        "timeline_items_synced",
    ):
        value = candidate.get(key)
        if value is not None:
            evidence[key] = value

    return evidence


def extract_acceptance_evidence(
    *,
    result_data: Dict[str, Any],
    result_json: Dict[str, Any],
    task: Optional[Any],
) -> Dict[str, Any]:
    """Extract acceptance evidence from task and result payloads."""
    task_result = getattr(task, "result", None)
    task_metadata = getattr(task, "metadata", None)
    task_pack_id = str(getattr(task, "pack_id", None) or "").strip()
    result_steps = result_data.get("steps") if isinstance(result_data, dict) else {}
    result_json_steps = (
        result_json.get("steps") if isinstance(result_json, dict) else {}
    )
    nested_result = (
        result_steps.get(task_pack_id)
        if isinstance(result_steps, dict) and task_pack_id
        else None
    )
    nested_result_json = (
        result_json_steps.get(task_pack_id)
        if isinstance(result_json_steps, dict) and task_pack_id
        else None
    )
    roots: List[Dict[str, Any]] = [
        nested_result if isinstance(nested_result, dict) else {},
        nested_result_json if isinstance(nested_result_json, dict) else {},
        result_data,
        result_json,
        result_data.get("outputs") if isinstance(result_data.get("outputs"), dict) else {},
        result_json.get("outputs") if isinstance(result_json.get("outputs"), dict) else {},
        result_data.get("metadata") if isinstance(result_data.get("metadata"), dict) else {},
        result_json.get("metadata") if isinstance(result_json.get("metadata"), dict) else {},
        task_result if isinstance(task_result, dict) else {},
        task_metadata if isinstance(task_metadata, dict) else {},
    ]
    evidence = first_nested_value(
        roots,
        [
            "outputs.acceptance_evidence",
            "acceptance_evidence",
            "metadata.acceptance_evidence",
        ],
    )
    if not isinstance(evidence, dict) or not evidence:
        for root in roots:
            if not isinstance(root, dict):
                continue
            outputs = root.get("outputs")
            for candidate in (
                outputs if isinstance(outputs, dict) else {},
                root,
            ):
                storyboard_evidence = extract_storyboard_preview_evidence(
                    candidate,
                    task_pack_id=task_pack_id,
                )
                if storyboard_evidence:
                    return storyboard_evidence
        return {}
    evidence = dict(evidence)
    if task_pack_id and not evidence.get("playbook_code"):
        evidence["playbook_code"] = task_pack_id
    return evidence


def extract_workflow_failure(
    *,
    result_data: Optional[Dict[str, Any]],
    execution_context: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Extract workflow failure text from result payloads."""
    def from_payload(payload: Optional[Dict[str, Any]]) -> Optional[str]:
        if not isinstance(payload, dict):
            return None

        status = str(payload.get("status") or "").strip().lower()
        if status in {"failed", "error"}:
            message = clean_string(payload.get("error")) or clean_string(
                payload.get("message")
            )
            if message:
                return message

        for steps_key in ("steps", "step_outputs"):
            steps = payload.get(steps_key)
            if not isinstance(steps, dict):
                continue
            for step_id, step_result in steps.items():
                if not isinstance(step_result, dict):
                    continue
                step_status = str(step_result.get("status") or "").strip().lower()
                step_error = clean_string(step_result.get("error"))
                if step_status in {"failed", "error"} or step_error:
                    return step_error or f"workflow step {step_id} failed"

        metadata = payload.get("metadata")
        if isinstance(metadata, dict):
            metadata_failure = from_payload(metadata)
            if metadata_failure:
                return metadata_failure
        if status in {"failed", "error"}:
            return "workflow failed"
        return None

    failure = from_payload(result_data)
    if failure:
        return failure

    workflow_result = (
        execution_context.get("workflow_result")
        if isinstance(execution_context, dict)
        else None
    )
    return from_payload(workflow_result)


def should_override_artifact_title(title: Optional[str]) -> bool:
    """Return True when an existing artifact title can be replaced."""
    normalized = clean_string(title)
    return normalized is None or normalized.startswith("Task Result:")
