"""Playbook-specific artifact extraction helpers."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _write_generated_artifact(
    service: Any,
    *,
    task: Any,
    playbook_code: str,
    intent_id: Optional[str],
    artifact_type: ArtifactType,
    title: str,
    content_bytes: bytes,
    log_label: str,
) -> tuple[Optional[str], bool, Optional[str]]:
    """Write generated artifact bytes into workspace storage."""
    storage_ref = None
    write_failed = False
    write_error = None

    try:
        storage_path = service._get_artifact_storage_path(
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            intent_id=intent_id,
            artifact_type=artifact_type.value,
        )

        filename = service._generate_artifact_filename(
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type.value,
            title=title,
        )

        target_path = storage_path / filename
        conflict_info = service._check_file_conflict(
            target_path=target_path,
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type.value,
        )

        if conflict_info.get("has_conflict") and conflict_info.get("suggested_version"):
            filename = service._generate_artifact_filename(
                workspace_id=task.workspace_id,
                playbook_code=playbook_code,
                artifact_type=artifact_type.value,
                title=title,
                version=conflict_info["suggested_version"],
            )
            target_path = storage_path / filename

        service._write_artifact_file_atomic(content_bytes, target_path)
        storage_ref = str(target_path)
        logger.info("Successfully wrote %s artifact to %s", log_label, storage_ref)
    except Exception as exc:
        write_failed = True
        write_error = str(exc)
        logger.warning(
            "Failed to write %s artifact to workspace path: %s. "
            "Artifact will be created without file storage.",
            log_label,
            exc,
        )

    return storage_ref, write_failed, write_error


def _copy_source_file_artifact(
    service: Any,
    *,
    task: Any,
    source_file_path: str,
    playbook_code: str,
    intent_id: Optional[str],
    artifact_type: ArtifactType,
    title: str,
    log_label: str,
) -> str:
    """Copy an existing source file into workspace storage, with fallback."""
    try:
        storage_dir = service._get_artifact_storage_path(
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            intent_id=intent_id,
            artifact_type=artifact_type.value,
        )
    except (ValueError, PermissionError) as exc:
        logger.error("Failed to get storage path for %s artifact: %s", log_label, exc)
        logger.warning("Using original file path as storage_ref: %s", source_file_path)
        return source_file_path

    filename = service._generate_artifact_filename(
        workspace_id=task.workspace_id,
        playbook_code=playbook_code,
        artifact_type=artifact_type.value,
        title=title,
    )
    target_path = storage_dir / filename

    conflict_info = service._check_file_conflict(
        target_path=target_path,
        workspace_id=task.workspace_id,
        playbook_code=playbook_code,
        artifact_type=artifact_type.value,
        force=False,
    )

    if conflict_info.get("has_conflict") and conflict_info.get("suggested_version"):
        filename = service._generate_artifact_filename(
            workspace_id=task.workspace_id,
            playbook_code=playbook_code,
            artifact_type=artifact_type.value,
            title=title,
            version=conflict_info["suggested_version"],
        )
        target_path = storage_dir / filename

    try:
        with service._file_lock(storage_dir):
            source_path = Path(source_file_path)
            if not source_path.exists():
                logger.warning(
                    "Source file not found: %s, using original path",
                    source_file_path,
                )
                return source_file_path

            file_content = source_path.read_bytes()
            service._write_artifact_file_atomic(file_content, target_path)
            storage_ref = str(target_path)
            logger.info("Successfully wrote %s artifact to %s", log_label, storage_ref)
            return storage_ref
    except Exception as exc:
        logger.error("Failed to write %s artifact file: %s, using original path", log_label, exc)
        return source_file_path


def extract_daily_planning_artifact(
    service: Any,
    task: Any,
    execution_result: Dict[str, Any],
    intent_id: Optional[str],
) -> Optional[Artifact]:
    """Extract checklist artifact from daily planning output."""
    tasks = execution_result.get("tasks", [])
    extraction_error = execution_result.get("extraction_error")
    checklist_items = []

    if not tasks:
        error_message = extraction_error or "No actionable tasks found in the content"
        logger.warning(
            "daily_planning: No tasks found in execution_result. "
            "execution_result keys: %s, tasks value: %s, title: %s, summary: %s, "
            "message: %s, extraction_error: %s",
            list(execution_result.keys()),
            execution_result.get("tasks"),
            execution_result.get("title"),
            execution_result.get("summary"),
            execution_result.get("message"),
            extraction_error,
        )
        checklist_items = [
            {
                "id": str(uuid.uuid4()),
                "title": f"⚠️ {error_message}",
                "description": (
                    "No actionable tasks were found in the content. "
                    "Please check the input or try again with more specific content."
                ),
                "priority": "",
                "completed": False,
            }
        ]
    else:
        for idx, task_item in enumerate(tasks[:10], 1):
            if isinstance(task_item, dict):
                title = task_item.get("title") or task_item.get("task") or f"Task {idx}"
                description = task_item.get("description") or task_item.get("details") or ""
                priority = task_item.get("priority") or task_item.get("urgency") or ""
                checklist_items.append(
                    {
                        "id": task_item.get("id") or str(uuid.uuid4()),
                        "title": title,
                        "description": description,
                        "priority": priority,
                        "completed": False,
                    }
                )
            elif isinstance(task_item, str):
                checklist_items.append(
                    {
                        "id": str(uuid.uuid4()),
                        "title": task_item,
                        "description": "",
                        "priority": "",
                        "completed": False,
                    }
                )

    if not checklist_items:
        logger.warning(
            "daily_planning: No checklist items created from tasks. "
            "tasks: %s, tasks type: %s, tasks length: %s",
            tasks,
            type(tasks),
            len(tasks) if isinstance(tasks, list) else "N/A",
        )
        return None

    if not tasks:
        error_message = extraction_error or "No actionable tasks found in the content"
        title = execution_result.get("title") or "Task extraction completed"
        summary = execution_result.get("summary") or f"No tasks extracted: {error_message}"
    else:
        title = execution_result.get("title") or f"Daily Planning - {len(checklist_items)} tasks"
        summary = execution_result.get("summary") or f"Extracted {len(checklist_items)} tasks"

    content_bytes = json.dumps(
        {
            "tasks": checklist_items,
            "total_count": len(checklist_items),
            "files_processed": execution_result.get("files_processed", 0),
            "title": title,
            "summary": summary,
        },
        indent=2,
        ensure_ascii=False,
    ).encode("utf-8")

    storage_ref, write_failed, write_error = _write_generated_artifact(
        service,
        task=task,
        playbook_code="daily_planning",
        intent_id=intent_id,
        artifact_type=ArtifactType.CHECKLIST,
        title=title,
        content_bytes=content_bytes,
        log_label="checklist",
    )

    metadata = {
        "extracted_at": _utc_now().isoformat(),
        "source": "daily_planning",
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
        playbook_code="daily_planning",
        artifact_type=ArtifactType.CHECKLIST,
        title=title,
        summary=summary,
        content={
            "tasks": checklist_items,
            "total_count": len(checklist_items),
            "files_processed": execution_result.get("files_processed", 0),
        },
        storage_ref=storage_ref,
        sync_state=None,
        primary_action_type=PrimaryActionType.COPY,
        metadata=metadata,
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )


def extract_content_drafting_artifact(
    service: Any,
    task: Any,
    execution_result: Dict[str, Any],
    intent_id: Optional[str],
) -> Optional[Artifact]:
    """Extract draft or summary artifacts from content drafting output."""
    content = execution_result.get("content")
    if content:
        title = execution_result.get("title") or "Generated Draft"
        summary = execution_result.get("summary") or (
            f"Draft in {execution_result.get('format', 'blog_post')} format"
        )

        storage_ref, write_failed, write_error = _write_generated_artifact(
            service,
            task=task,
            playbook_code="content_drafting",
            intent_id=intent_id,
            artifact_type=ArtifactType.DRAFT,
            title=title,
            content_bytes=content.encode("utf-8"),
            log_label="draft",
        )

        metadata = {
            "extracted_at": _utc_now().isoformat(),
            "source": "content_drafting",
            "output_type": "draft",
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
            playbook_code="content_drafting",
            artifact_type=ArtifactType.DRAFT,
            title=title,
            summary=summary,
            content={
                "content": content,
                "format": execution_result.get("format", "blog_post"),
                "tags": execution_result.get("tags", []),
                "files_processed": execution_result.get("files_processed", 0),
            },
            storage_ref=storage_ref,
            sync_state=None,
            primary_action_type=PrimaryActionType.COPY,
            metadata=metadata,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )

    raw_summary = execution_result.get("summary") or ""
    raw_content = execution_result.get("content") or ""
    title = (
        execution_result.get("title")
        or execution_result.get("document_title")
        or (raw_summary.split("\n")[0][:100] if raw_summary else None)
        or (raw_content.split("\n")[0][:100] if raw_content else None)
        or "內容摘要"
    )

    if raw_summary and raw_summary.strip() and raw_summary.strip() != "Summary generated":
        summary = raw_summary[:200] if len(raw_summary) > 200 else raw_summary
    elif raw_content:
        content_lines = [line.strip() for line in raw_content.split("\n") if line.strip()]
        if content_lines:
            summary = content_lines[0][:200] if len(content_lines[0]) > 200 else content_lines[0]
        else:
            summary = "已生成內容摘要"
    else:
        summary = "已生成內容摘要"

    summary_content = raw_summary or raw_content or summary
    if execution_result.get("key_points"):
        summary_content += "\n\nKey Points:\n" + "\n".join(
            f"- {point}" for point in execution_result.get("key_points", [])
        )
    if execution_result.get("themes"):
        summary_content += "\n\nThemes:\n" + "\n".join(
            f"- {theme}" for theme in execution_result.get("themes", [])
        )

    return Artifact(
        id=str(uuid.uuid4()),
        workspace_id=task.workspace_id,
        intent_id=intent_id,
        task_id=task.id,
        execution_id=task.execution_id,
        playbook_code="content_drafting",
        artifact_type=ArtifactType.DRAFT,
        title=title,
        summary=summary,
        content={
            "content": summary_content,
            "key_points": execution_result.get("key_points", []),
            "themes": execution_result.get("themes", []),
            "files_processed": execution_result.get("files_processed", 0),
        },
        storage_ref=None,
        sync_state=None,
        primary_action_type=PrimaryActionType.COPY,
        metadata={
            "extracted_at": _utc_now().isoformat(),
            "source": "content_drafting",
            "output_type": "summary",
        },
        created_at=_utc_now(),
        updated_at=_utc_now(),
    )


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
