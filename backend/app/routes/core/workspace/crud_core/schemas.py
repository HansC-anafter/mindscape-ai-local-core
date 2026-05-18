
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from backend.app.models.workspace import Workspace

class WorkspaceSummary(BaseModel):
    id: str
    owner_user_id: str
    title: str
    description: Optional[str] = None
    workspace_type: Optional[str] = None
    group_id: Optional[str] = None
    workspace_role: Optional[str] = None
    primary_project_id: Optional[str] = None
    default_playbook_id: Optional[str] = None
    default_locale: Optional[str] = None
    mode: Optional[str] = None
    storage_base_path: Optional[str] = None
    artifacts_dir: Optional[str] = None
    uploads_dir: Optional[str] = None
    storage_config: Optional[Dict[str, Any]] = None
    playbook_storage_config: Optional[Dict[str, Any]] = None
    playbook_auto_execution_config: Optional[Dict[str, Any]] = None
    workspace_blueprint: Optional[Dict[str, Any]] = None
    execution_mode: Optional[str] = None
    meeting_enabled: bool = False
    expected_artifacts: Optional[List[str]] = None
    execution_priority: Optional[str] = None
    project_assignment_mode: Optional[str] = None
    launch_status: Optional[str] = None
    starter_kit_type: Optional[str] = None
    ttl_hours: Optional[int] = None
    expires_at: Optional[datetime] = None
    parent_workspace_id: Optional[str] = None
    visibility: Optional[str] = None
    created_at: datetime
    updated_at: datetime


def _workspace_to_summary(workspace: Workspace) -> WorkspaceSummary:
    workspace_type = getattr(workspace, "workspace_type", None)
    project_assignment_mode = getattr(workspace, "project_assignment_mode", None)
    launch_status = getattr(workspace, "launch_status", None)
    visibility = getattr(workspace, "visibility", None)

    return WorkspaceSummary(
        id=workspace.id,
        owner_user_id=workspace.owner_user_id,
        title=workspace.title,
        description=workspace.description,
        workspace_type=getattr(workspace_type, "value", workspace_type),
        group_id=getattr(workspace, "group_id", None),
        workspace_role=getattr(workspace, "workspace_role", None),
        primary_project_id=workspace.primary_project_id,
        default_playbook_id=workspace.default_playbook_id,
        default_locale=workspace.default_locale,
        mode=workspace.mode,
        storage_base_path=workspace.storage_base_path,
        artifacts_dir=workspace.artifacts_dir,
        uploads_dir=workspace.uploads_dir,
        storage_config=workspace.storage_config,
        playbook_storage_config=workspace.playbook_storage_config,
        playbook_auto_execution_config=workspace.playbook_auto_execution_config,
        workspace_blueprint=(
            workspace.workspace_blueprint.model_dump()
            if workspace.workspace_blueprint
            else None
        ),
        execution_mode=workspace.execution_mode,
        meeting_enabled=bool(getattr(workspace, "meeting_enabled", False)),
        expected_artifacts=workspace.expected_artifacts,
        execution_priority=workspace.execution_priority,
        project_assignment_mode=getattr(
            project_assignment_mode, "value", project_assignment_mode
        ),
        launch_status=getattr(launch_status, "value", launch_status),
        starter_kit_type=workspace.starter_kit_type,
        ttl_hours=getattr(workspace, "ttl_hours", None),
        expires_at=getattr(workspace, "expires_at", None),
        parent_workspace_id=getattr(workspace, "parent_workspace_id", None),
        visibility=getattr(visibility, "value", visibility),
        created_at=workspace.created_at,
        updated_at=workspace.updated_at,
    )
