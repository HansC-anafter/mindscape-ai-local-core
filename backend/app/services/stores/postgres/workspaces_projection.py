"""Projection helpers for Postgres workspace rows."""

from __future__ import annotations

from typing import Any, Callable, Dict

from app.models.workspace import (
    LaunchStatus,
    ProjectAssignmentMode,
    Workspace,
    WorkspaceType,
    WorkspaceVisibility,
)
from app.models.workspace_blueprint import WorkspaceBlueprint

DeserializeJson = Callable[..., Any]

DATA_SOURCE_SUMMARY_LIMIT = 500


def row_to_workspace_summary(
    row: Any,
    *,
    deserialize_json: DeserializeJson,
) -> Dict[str, Any]:
    return {
        "id": row.id,
        "owner_user_id": row.owner_user_id,
        "title": row.title,
        "description": row.description,
        "workspace_type": row.workspace_type or "personal",
        "group_id": None,
        "workspace_role": None,
        "group_memberships": [],
        "primary_project_id": row.primary_project_id,
        "default_playbook_id": row.default_playbook_id,
        "default_locale": row.default_locale,
        "mode": row.mode,
        "storage_base_path": getattr(row, "storage_base_path", None),
        "artifacts_dir": getattr(row, "artifacts_dir", None),
        "uploads_dir": getattr(row, "uploads_dir", None),
        "storage_config": deserialize_json(getattr(row, "storage_config", None)),
        "playbook_storage_config": deserialize_json(
            getattr(row, "playbook_storage_config", None)
        ),
        "playbook_auto_execution_config": deserialize_json(
            getattr(row, "playbook_auto_execution_config", None)
        ),
        "workspace_blueprint": deserialize_json(
            getattr(row, "workspace_blueprint", None)
        ),
        "execution_mode": row.execution_mode or "qa",
        "meeting_enabled": bool(getattr(row, "meeting_enabled", False)),
        "expected_artifacts": deserialize_json(row.expected_artifacts, default=[]),
        "execution_priority": row.execution_priority or "medium",
        "project_assignment_mode": row.project_assignment_mode or "auto_silent",
        "launch_status": row.launch_status or LaunchStatus.PENDING.value,
        "starter_kit_type": row.starter_kit_type,
        "ttl_hours": getattr(row, "ttl_hours", None),
        "expires_at": getattr(row, "expires_at", None),
        "parent_workspace_id": getattr(row, "parent_workspace_id", None),
        "visibility": getattr(row, "visibility", None) or "private",
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def row_to_workspace(
    row: Any,
    *,
    deserialize_json: DeserializeJson,
    logger: Any,
) -> Workspace:
    try:
        workspace_type = WorkspaceType(row.workspace_type or "personal")
    except ValueError:
        workspace_type = WorkspaceType.PERSONAL

    try:
        project_assignment_mode = ProjectAssignmentMode(
            row.project_assignment_mode or "auto_silent"
        )
    except ValueError:
        project_assignment_mode = ProjectAssignmentMode.AUTO_SILENT

    try:
        launch_status = LaunchStatus(row.launch_status or "pending")
    except ValueError:
        launch_status = LaunchStatus.PENDING

    blueprint_data = deserialize_json(row.workspace_blueprint)
    workspace_blueprint = None
    if blueprint_data:
        try:
            workspace_blueprint = WorkspaceBlueprint.model_validate(blueprint_data)
        except Exception as exc:
            logger.warning(
                "Failed to validate workspace_blueprint for %s: %s",
                row.id,
                exc,
            )

    return Workspace(
        id=row.id,
        owner_user_id=row.owner_user_id,
        title=row.title,
        description=row.description,
        workspace_type=workspace_type,
        group_id=None,
        workspace_role=None,
        group_memberships=[],
        primary_project_id=row.primary_project_id,
        default_playbook_id=row.default_playbook_id,
        default_locale=row.default_locale,
        mode=row.mode,
        data_sources=deserialize_json(row.data_sources),
        playbook_auto_execution_config=deserialize_json(
            row.playbook_auto_execution_config
        ),
        suggestion_history=deserialize_json(row.suggestion_history, default=[]),
        storage_base_path=row.storage_base_path,
        artifacts_dir=row.artifacts_dir,
        uploads_dir=row.uploads_dir,
        storage_config=deserialize_json(row.storage_config),
        playbook_storage_config=deserialize_json(row.playbook_storage_config),
        execution_mode=row.execution_mode or "qa",
        meeting_enabled=bool(getattr(row, "meeting_enabled", False)),
        expected_artifacts=deserialize_json(row.expected_artifacts, default=[]),
        execution_priority=row.execution_priority or "medium",
        project_assignment_mode=project_assignment_mode,
        metadata=deserialize_json(row.metadata, {}),
        workspace_blueprint=workspace_blueprint,
        launch_status=launch_status,
        starter_kit_type=row.starter_kit_type,
        sandbox_config=deserialize_json(getattr(row, "sandbox_config", None)),
        ttl_hours=getattr(row, "ttl_hours", None),
        expires_at=getattr(row, "expires_at", None),
        parent_workspace_id=getattr(row, "parent_workspace_id", None),
        visibility=WorkspaceVisibility(getattr(row, "visibility", None) or "private"),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def compact_data_source_entry(
    entry: Dict[str, Any],
    *,
    summary_limit: int = DATA_SOURCE_SUMMARY_LIMIT,
) -> Dict[str, Any]:
    compacted = dict(entry or {})
    summary = compacted.get("last_result_summary")
    if summary is None:
        return compacted
    summary_text = str(summary).strip()
    if len(summary_text) > summary_limit:
        summary_text = summary_text[: summary_limit - 3].rstrip() + "..."
    compacted["last_result_summary"] = summary_text
    return compacted
