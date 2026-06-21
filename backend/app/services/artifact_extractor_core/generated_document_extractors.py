"""Generated document artifact extraction helpers."""

from __future__ import annotations

import json
import logging
import uuid
from typing import Any, Dict, Optional

from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services.artifact_extractor_core.artifact_file_storage import (
    _utc_now,
    _write_generated_artifact,
)

logger = logging.getLogger("backend.app.services.artifact_extractor_core.extractors")


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
