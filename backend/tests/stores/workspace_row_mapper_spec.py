import json
from datetime import datetime

from backend.app.models.workspace import LaunchStatus, ProjectAssignmentMode, WorkspaceType
from backend.app.services.stores.workspace_row_mapper import row_to_workspace


def _deserialize_json(value, default=None):
    if not value:
        return default
    return json.loads(value)


def test_row_to_workspace_maps_full_legacy_row():
    row = {
        "id": "workspace-1",
        "owner_user_id": "user-1",
        "title": "Research Desk",
        "description": "Demo",
        "workspace_type": "brand",
        "primary_project_id": "project-1",
        "default_playbook_id": "playbook-1",
        "default_locale": "zh-TW",
        "mode": "research",
        "data_sources": json.dumps({"local_folder": "/tmp/demo"}),
        "playbook_auto_execution_config": json.dumps({"p": {"auto_execute": True}}),
        "suggestion_history": json.dumps([{"round_id": "r1"}]),
        "storage_base_path": "/tmp/workspace",
        "artifacts_dir": "artifacts",
        "uploads_dir": "uploads",
        "storage_config": json.dumps({"bucket": "local"}),
        "playbook_storage_config": json.dumps({"p": {"base_path": "/tmp/p"}}),
        "execution_mode": "execution",
        "expected_artifacts": json.dumps(["docx"]),
        "execution_priority": "high",
        "project_assignment_mode": "assistive",
        "metadata": json.dumps({"team": "core"}),
        "workspace_blueprint": None,
        "launch_status": "active",
        "starter_kit_type": "custom",
        "created_at": "2026-06-16T01:00:00+00:00",
        "updated_at": "2026-06-16T02:00:00+00:00",
    }

    workspace = row_to_workspace(
        row,
        deserialize_json=_deserialize_json,
        from_isoformat=datetime.fromisoformat,
    )

    assert workspace.workspace_type == WorkspaceType.BRAND
    assert workspace.project_assignment_mode == ProjectAssignmentMode.ASSISTIVE
    assert workspace.launch_status == LaunchStatus.ACTIVE
    assert workspace.data_sources == {"local_folder": "/tmp/demo"}
    assert workspace.expected_artifacts == ["docx"]
    assert workspace.metadata == {"team": "core"}
    assert workspace.updated_at.isoformat() == "2026-06-16T02:00:00+00:00"


def test_row_to_workspace_preserves_legacy_defaults_when_columns_are_missing():
    row = {
        "id": "workspace-2",
        "owner_user_id": "user-1",
        "title": "Legacy Workspace",
        "description": None,
        "primary_project_id": None,
        "default_playbook_id": None,
        "default_locale": None,
        "created_at": "2026-06-16T01:00:00+00:00",
        "updated_at": "2026-06-16T02:00:00+00:00",
    }

    workspace = row_to_workspace(
        row,
        deserialize_json=_deserialize_json,
        from_isoformat=datetime.fromisoformat,
    )

    assert workspace.workspace_type == WorkspaceType.PERSONAL
    assert workspace.project_assignment_mode == ProjectAssignmentMode.AUTO_SILENT
    assert workspace.launch_status == LaunchStatus.PENDING
    assert workspace.execution_mode == "qa"
    assert workspace.execution_priority == "medium"
    assert workspace.metadata == {}
