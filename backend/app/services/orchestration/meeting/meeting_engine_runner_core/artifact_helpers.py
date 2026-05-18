"""Artifact helper functions for MeetingEngineRunner."""

from __future__ import annotations

import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_command import MeetingCommandRecord
from backend.app.models.workspace import Artifact, ArtifactType as WorkspaceArtifactType
from backend.app.models.workspace import PrimaryActionType

def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}

def _artifact_payload(artifact: Any) -> Dict[str, Any]:
    if hasattr(artifact, "model_dump"):
        return artifact.model_dump(exclude_none=True)
    return dict(artifact) if isinstance(artifact, dict) else {}

def _artifact_file_path(payload: Dict[str, Any]) -> Optional[str]:
    metadata = _as_dict(payload.get("metadata"))
    for key in ("file_path", "actual_file_path", "storage_ref"):
        value = payload.get(key) or metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    uri = payload.get("uri")
    if isinstance(uri, str) and uri.startswith("/"):
        return uri
    return None

def _artifact_model_file_path(artifact: Any) -> Optional[str]:
    metadata = _as_dict(getattr(artifact, "metadata", None))
    for key in ("actual_file_path", "file_path", "storage_ref"):
        value = _clean_string(metadata.get(key))
        if value:
            return value
    storage_ref = _clean_string(getattr(artifact, "storage_ref", None))
    if storage_ref:
        return storage_ref
    return None

def _artifact_model_content(artifact: Any) -> Dict[str, Any]:
    return _as_dict(getattr(artifact, "content", None))

def _clean_string(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None

def _append_unique(values: List[str], value: Optional[str]) -> None:
    if value and value not in values:
        values.append(value)

def _dispatch_execution_ids(value: Any, *, depth: int = 0) -> List[str]:
    if depth > 8:
        return []
    found: List[str] = []
    if isinstance(value, dict):
        execution_id = _clean_string(value.get("execution_id"))
        if execution_id:
            found.append(execution_id)
        for nested in value.values():
            for nested_id in _dispatch_execution_ids(nested, depth=depth + 1):
                _append_unique(found, nested_id)
    elif isinstance(value, list):
        for item in value:
            for nested_id in _dispatch_execution_ids(item, depth=depth + 1):
                _append_unique(found, nested_id)
    return found

def _execution_artifact_failure_reason(artifact: Any) -> Optional[str]:
    content = _artifact_model_content(artifact)
    if not content:
        return None

    status = (_clean_string(content.get("status")) or "").lower()
    if status in {"error", "failed", "failure"}:
        return _clean_string(content.get("error")) or f"execution_status:{status}"

    steps = _as_dict(content.get("steps"))
    for step_id, raw_step in steps.items():
        step = _as_dict(raw_step)
        step_status = (_clean_string(step.get("status")) or "").lower()
        if step_status in {"error", "failed", "failure"}:
            reason = _clean_string(step.get("error")) or f"step_status:{step_status}"
            return f"step_failed:{step_id}:{reason}"

    result = _as_dict(content.get("result"))
    if result.get("success") is False:
        return _clean_string(result.get("error")) or "result_success_false"

    output = _as_dict(content.get("output"))
    if output.get("success") is False:
        return _clean_string(output.get("error")) or "output_success_false"

    return None

def _execution_artifacts(lookup_store: Any, execution_id: str) -> List[Any]:
    if hasattr(lookup_store, "list_by_execution_id"):
        artifacts = lookup_store.list_by_execution_id(execution_id)
        if artifacts is None:
            return []
        if isinstance(artifacts, list):
            return artifacts
        return list(artifacts)

    if hasattr(lookup_store, "get_by_execution_id"):
        artifact = lookup_store.get_by_execution_id(execution_id)
        return [artifact] if artifact is not None else []

    return []

def _workspace_artifact_type(payload: Dict[str, Any]) -> WorkspaceArtifactType:
    metadata = _as_dict(payload.get("metadata"))
    raw_type = _clean_string(
        metadata.get("workspace_artifact_type") or metadata.get("artifact_type")
    )
    if raw_type:
        try:
            return WorkspaceArtifactType(raw_type.lower())
        except ValueError:
            pass

    mime_type = _clean_string(payload.get("type") or metadata.get("mime_type")) or ""
    uri = _clean_string(payload.get("uri")) or ""
    candidate = f"{mime_type} {uri}".lower()
    if "image/" in candidate or candidate.endswith(
        (".png", ".jpg", ".jpeg", ".webp")
    ):
        return WorkspaceArtifactType.IMAGE
    if "video/" in candidate or candidate.endswith((".mp4", ".mov", ".webm")):
        return WorkspaceArtifactType.VIDEO
    if "audio/" in candidate or candidate.endswith((".mp3", ".wav", ".m4a")):
        return WorkspaceArtifactType.AUDIO
    if "json" in candidate:
        return WorkspaceArtifactType.DATA
    if (
        "markdown" in candidate
        or "text/" in candidate
        or candidate.endswith((".md", ".txt"))
    ):
        return WorkspaceArtifactType.DRAFT
    return WorkspaceArtifactType.FILE

def _workspace_primary_action_type(storage_ref: Optional[str]) -> PrimaryActionType:
    if storage_ref and storage_ref.startswith(("http://", "https://")):
        return PrimaryActionType.OPEN_EXTERNAL
    if storage_ref:
        return PrimaryActionType.DOWNLOAD
    return PrimaryActionType.PREVIEW

def _workspace_artifact_from_task_ir_payload(
    payload: Dict[str, Any],
    *,
    workspace_id: str,
    thread_id: str,
    task_id: Optional[str],
    command: MeetingCommandRecord,
    request_contract_aol: Dict[str, Any],
) -> Artifact:
    metadata = _as_dict(payload.get("metadata"))
    artifact_id = (
        _clean_string(payload.get("id"))
        or f"meeting_artifact_{uuid.uuid4().hex}"
    )
    storage_ref = _artifact_file_path(payload) or _clean_string(payload.get("uri"))
    title = (
        _clean_string(payload.get("title"))
        or _clean_string(metadata.get("title"))
        or artifact_id
    )
    summary = (
        _clean_string(payload.get("summary"))
        or _clean_string(metadata.get("summary"))
        or "Artifact produced by MeetingEngine orchestration."
    )
    source = (
        _clean_string(payload.get("source") or metadata.get("source"))
        or "meeting_engine"
    )
    playbook_code = (
        _clean_string(metadata.get("playbook_code"))
        or (source.split(":", 1)[1] if source.startswith("playbook:") else None)
        or "meeting_engine"
    )
    content = _as_dict(payload.get("content"))
    if not content:
        content = {"task_ir_artifact": payload}
    artifact_metadata = {
        **metadata,
        "meeting_id": command.meeting_id,
        "command_id": command.command_id,
        "thread_id": thread_id,
        "artifact_landing_source": "meeting_engine_task_ir",
        "source_task_ir_artifact": payload,
    }
    if request_contract_aol:
        artifact_metadata["request_contract_aol_metadata"] = request_contract_aol
    if storage_ref:
        artifact_metadata.setdefault("file_path", storage_ref)

    return Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        intent_id=_clean_string(metadata.get("intent_id")),
        task_id=task_id,
        execution_id=_clean_string(
            payload.get("execution_id") or metadata.get("execution_id") or task_id
        ),
        thread_id=thread_id,
        playbook_code=playbook_code,
        artifact_type=_workspace_artifact_type(payload),
        title=title,
        summary=summary,
        content=content,
        storage_ref=storage_ref,
        sync_state=None,
        primary_action_type=_workspace_primary_action_type(storage_ref),
        metadata=artifact_metadata,
    )
