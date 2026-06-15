"""
Workspace row projection helpers.

This module keeps legacy SQLite row compatibility logic out of the store while
leaving the store responsible for connection and transaction boundaries.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

from ...models.workspace import (
    LaunchStatus,
    ProjectAssignmentMode,
    Workspace,
    WorkspaceType,
)
from ...models.workspace_blueprint import WorkspaceBlueprint

logger = logging.getLogger(__name__)

DeserializeJson = Callable[[Optional[str], Any], Any]
FromIsoformat = Callable[[Optional[str]], Any]


def _optional_value(row: Any, key: str, default: Any = None) -> Any:
    try:
        value = row[key]
    except (KeyError, IndexError):
        return default
    return value if value else default


def _json_value(
    row: Any,
    key: str,
    deserialize_json: DeserializeJson,
    default: Any = None,
) -> Any:
    value = _optional_value(row, key)
    if value is None:
        return default
    return deserialize_json(value, default)


def _project_assignment_mode(row: Any) -> ProjectAssignmentMode:
    mode = _optional_value(row, "project_assignment_mode", "auto_silent")
    try:
        return ProjectAssignmentMode(mode)
    except ValueError:
        return ProjectAssignmentMode.AUTO_SILENT


def _workspace_type(row: Any) -> WorkspaceType:
    workspace_type = _optional_value(row, "workspace_type", "personal")
    try:
        return WorkspaceType(workspace_type)
    except ValueError:
        return WorkspaceType.PERSONAL


def _workspace_blueprint(row: Any, deserialize_json: DeserializeJson) -> Optional[WorkspaceBlueprint]:
    blueprint_data = _json_value(row, "workspace_blueprint", deserialize_json, None)
    if not blueprint_data:
        return None
    try:
        return WorkspaceBlueprint.model_validate(blueprint_data)
    except ValueError as exc:
        logger.warning(f"Failed to deserialize workspace_blueprint: {exc}")
        return None


def _launch_status(row: Any) -> LaunchStatus:
    launch_status = _optional_value(row, "launch_status", "pending")
    try:
        return LaunchStatus(launch_status)
    except ValueError:
        return LaunchStatus.PENDING


def row_to_workspace(
    row: Any,
    *,
    deserialize_json: DeserializeJson,
    from_isoformat: FromIsoformat,
) -> Workspace:
    """Convert a legacy workspace row into a Workspace model."""

    return Workspace(
        id=row["id"],
        owner_user_id=row["owner_user_id"],
        title=row["title"],
        description=_optional_value(row, "description"),
        workspace_type=_workspace_type(row),
        primary_project_id=_optional_value(row, "primary_project_id"),
        default_playbook_id=_optional_value(row, "default_playbook_id"),
        default_locale=_optional_value(row, "default_locale"),
        mode=_optional_value(row, "mode"),
        data_sources=_json_value(row, "data_sources", deserialize_json, None),
        playbook_auto_execution_config=_json_value(
            row,
            "playbook_auto_execution_config",
            deserialize_json,
            None,
        ),
        suggestion_history=_json_value(row, "suggestion_history", deserialize_json, None),
        storage_base_path=_optional_value(row, "storage_base_path"),
        artifacts_dir=_optional_value(row, "artifacts_dir"),
        uploads_dir=_optional_value(row, "uploads_dir"),
        storage_config=_json_value(row, "storage_config", deserialize_json, None),
        playbook_storage_config=_json_value(
            row,
            "playbook_storage_config",
            deserialize_json,
            None,
        ),
        execution_mode=_optional_value(row, "execution_mode", "qa"),
        expected_artifacts=_json_value(row, "expected_artifacts", deserialize_json, None),
        execution_priority=_optional_value(row, "execution_priority", "medium"),
        project_assignment_mode=_project_assignment_mode(row),
        metadata=_json_value(row, "metadata", deserialize_json, {}),
        workspace_blueprint=_workspace_blueprint(row, deserialize_json),
        launch_status=_launch_status(row),
        starter_kit_type=_optional_value(row, "starter_kit_type"),
        created_at=from_isoformat(row["created_at"]),
        updated_at=from_isoformat(row["updated_at"]),
    )
