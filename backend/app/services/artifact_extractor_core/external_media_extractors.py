"""External and media artifact extraction helpers."""

from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services.artifact_extractor_core.artifact_file_storage import (
    _copy_source_file_artifact,
    _utc_now,
    _write_generated_artifact,
)

logger = logging.getLogger("backend.app.services.artifact_extractor_core.extractors")


def extract_major_proposal_artifact(
    service: Any,
    task: Any,
    execution_result: Dict[str, Any],
    intent_id: Optional[str],
) -> Optional[Artifact]:
    """Extract a proposal DOCX artifact from execution output."""
    source_file_path = execution_result.get("file_path") or execution_result.get("docx_path")
    if not source_file_path:
        logger.debug("major_proposal: No file_path found in execution_result")
        return None

    title = execution_result.get("title") or "Proposal Document"
    summary = execution_result.get("summary") or "Generated proposal document"
    storage_ref = _copy_source_file_artifact(
        service,
        task=task,
        source_file_path=source_file_path,
        playbook_code="major_proposal_writing",
        intent_id=intent_id,
        artifact_type=ArtifactType.DOCX,
        title=title,
        log_label="DOCX",
    )

    return Artifact(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        intent_id=intent_id,
        task_id=task.id,
        execution_id=task.execution_id,
        playbook_code="major_proposal_writing",
        artifact_type=ArtifactType.DOCX,
        title=title,
        summary=summary,
        content={
            "file_path": storage_ref,
            "file_name": Path(storage_ref).name,
            "original_path": source_file_path,
        },
        storage_ref=storage_ref,
        sync_state=None,
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata={
            "extracted_at": _utc_now().isoformat(),
            "source": "major_proposal_writing",
        },
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )


def extract_campaign_asset_artifact(
    service: Any,
    task: Any,
    execution_result: Dict[str, Any],
    intent_id: Optional[str],
) -> Optional[Artifact]:
    """Extract a Canva/external design artifact."""
    del service

    canva_url = (
        execution_result.get("canva_url")
        or execution_result.get("url")
        or execution_result.get("design_url")
    )
    if not canva_url:
        logger.debug("campaign_asset: No canva_url found in execution_result")
        return None

    title = execution_result.get("title") or "Campaign Asset"
    summary = execution_result.get("summary") or "Canva design created"

    return Artifact(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        intent_id=intent_id,
        task_id=task.id,
        execution_id=task.execution_id,
        playbook_code="campaign_asset_playbook",
        artifact_type=ArtifactType.CANVA,
        title=title,
        summary=summary,
        content={
            "canva_url": canva_url,
            "thumbnail_url": execution_result.get("thumbnail_url"),
            "design_id": execution_result.get("design_id"),
        },
        storage_ref=canva_url,
        sync_state=None,
        primary_action_type=PrimaryActionType.OPEN_EXTERNAL,
        metadata={
            "extracted_at": _utc_now().isoformat(),
            "source": "campaign_asset_playbook",
        },
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )


def extract_audio_artifact(
    service: Any,
    task: Any,
    execution_result: Dict[str, Any],
    intent_id: Optional[str],
) -> Optional[Artifact]:
    """Extract an audio artifact from execution output."""
    source_audio_path = (
        execution_result.get("audio_file_path")
        or execution_result.get("file_path")
        or execution_result.get("audio_path")
    )
    if not source_audio_path:
        logger.debug("audio: No audio_file_path found in execution_result")
        return None

    title = execution_result.get("title") or "Audio Recording"
    summary = execution_result.get("summary") or "Audio recording completed"
    storage_ref = _copy_source_file_artifact(
        service,
        task=task,
        source_file_path=source_audio_path,
        playbook_code="ai_guided_recording",
        intent_id=intent_id,
        artifact_type=ArtifactType.AUDIO,
        title=title,
        log_label="audio",
    )

    return Artifact(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        intent_id=intent_id,
        task_id=task.id,
        execution_id=task.execution_id,
        playbook_code="ai_guided_recording",
        artifact_type=ArtifactType.AUDIO,
        title=title,
        summary=summary,
        content={
            "audio_file_path": storage_ref,
            "transcript": execution_result.get("transcript"),
            "duration": execution_result.get("duration"),
            "file_size": execution_result.get("file_size"),
            "original_path": source_audio_path,
        },
        storage_ref=storage_ref,
        sync_state=None,
        primary_action_type=PrimaryActionType.DOWNLOAD,
        metadata={
            "extracted_at": _utc_now().isoformat(),
            "source": "ai_guided_recording",
        },
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )


def extract_generic_artifact(
    service: Any,
    task: Any,
    execution_result: Dict[str, Any],
    playbook_code: str,
    intent_id: Optional[str],
) -> Optional[Artifact]:
    """Extract a generic fallback artifact from an unknown playbook."""
    title = execution_result.get("title")
    summary = execution_result.get("summary") or execution_result.get("message")
    content = execution_result.get("content") or execution_result.get("result")

    if not (title or summary or content):
        logger.debug("generic: No extractable content found for playbook %s", playbook_code)
        return None

    artifact_type = ArtifactType.DRAFT
    primary_action = PrimaryActionType.COPY

    if execution_result.get("file_path") or execution_result.get("docx_path"):
        artifact_type = ArtifactType.DOCX
        primary_action = PrimaryActionType.DOWNLOAD
    elif execution_result.get("canva_url") or execution_result.get("url"):
        artifact_type = ArtifactType.CANVA
        primary_action = PrimaryActionType.OPEN_EXTERNAL
    elif execution_result.get("tasks") or execution_result.get("checklist"):
        artifact_type = ArtifactType.CHECKLIST
        primary_action = PrimaryActionType.COPY

    storage_ref = execution_result.get("file_path") or execution_result.get("storage_ref")
    write_failed = False
    write_error = None

    if not storage_ref:
        if artifact_type == ArtifactType.DRAFT:
            content_str = content if isinstance(content, str) else str(content)
            content_bytes = content_str.encode("utf-8")
        else:
            content_bytes = json.dumps(
                execution_result,
                indent=2,
                ensure_ascii=False,
            ).encode("utf-8")

        storage_ref, write_failed, write_error = _write_generated_artifact(
            service,
            task=task,
            playbook_code=playbook_code,
            intent_id=intent_id,
            artifact_type=artifact_type,
            title=title or playbook_code,
            content_bytes=content_bytes,
            log_label="generic",
        )

    metadata = {
        "extracted_at": _utc_now().isoformat(),
        "source": "generic_extraction",
        "playbook_code": playbook_code,
    }
    if write_failed:
        metadata["write_failed"] = True
        metadata["write_error"] = write_error

    return Artifact(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        intent_id=intent_id,
        task_id=task.id,
        execution_id=task.execution_id,
        playbook_code=playbook_code,
        artifact_type=artifact_type,
        title=title or playbook_code,
        summary=summary or f"Output from {playbook_code}",
        content=execution_result,
        storage_ref=storage_ref,
        sync_state=None,
        primary_action_type=primary_action,
        metadata=metadata,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )
