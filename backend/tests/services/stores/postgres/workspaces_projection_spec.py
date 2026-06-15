import json
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.models.workspace import (
    LaunchStatus,
    ProjectAssignmentMode,
    WorkspaceType,
)
from backend.app.services.stores.postgres.workspaces_projection import (
    compact_data_source_entry,
    row_to_workspace,
    row_to_workspace_summary,
)


class RecordingLogger:
    def __init__(self):
        self.warnings = []

    def warning(self, message, *args):
        self.warnings.append(message % args if args else message)


def _deserialize_json(value, default=None):
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        return value
    return json.loads(value)


def _workspace_row(**overrides):
    now = datetime(2026, 6, 16, 1, 0, tzinfo=timezone.utc)
    row = {
        "id": "workspace-1",
        "owner_user_id": "user-1",
        "title": "Demo Workspace",
        "description": "Demo",
        "workspace_type": "brand",
        "group_id": "group-1",
        "workspace_role": "cell",
        "primary_project_id": "project-1",
        "default_playbook_id": "playbook-1",
        "default_locale": "zh-TW",
        "mode": "research",
        "data_sources": json.dumps({"pack": {"total_runs": 1}}),
        "playbook_auto_execution_config": json.dumps({"demo": {"auto": True}}),
        "suggestion_history": json.dumps([{"id": "s1"}]),
        "storage_base_path": "/tmp/workspace",
        "artifacts_dir": "artifacts",
        "uploads_dir": "uploads",
        "storage_config": json.dumps({"bucket": "local"}),
        "playbook_storage_config": json.dumps({"demo": {"base_path": "/tmp/demo"}}),
        "workspace_blueprint": None,
        "execution_mode": "execution",
        "meeting_enabled": True,
        "expected_artifacts": json.dumps(["docx"]),
        "execution_priority": "high",
        "project_assignment_mode": "assistive",
        "metadata": json.dumps({"team": "core"}),
        "launch_status": "active",
        "starter_kit_type": "custom",
        "sandbox_config": json.dumps({"filesystem_scope": ["/tmp"]}),
        "ttl_hours": 4,
        "expires_at": None,
        "parent_workspace_id": None,
        "visibility": "private",
        "created_at": now,
        "updated_at": now,
    }
    row.update(overrides)
    return SimpleNamespace(**row)


def test_row_to_workspace_summary_keeps_lightweight_shape():
    summary = row_to_workspace_summary(
        _workspace_row(),
        deserialize_json=_deserialize_json,
    )

    assert "data_sources" not in summary
    assert "metadata" not in summary
    assert summary["workspace_type"] == "brand"
    assert summary["expected_artifacts"] == ["docx"]
    assert summary["meeting_enabled"] is True
    assert summary["visibility"] == "private"


def test_row_to_workspace_projects_full_model_and_enum_fallbacks():
    workspace = row_to_workspace(
        _workspace_row(
            workspace_type="unknown",
            project_assignment_mode="unknown",
            launch_status="unknown",
        ),
        deserialize_json=_deserialize_json,
        logger=RecordingLogger(),
    )

    assert workspace.workspace_type == WorkspaceType.PERSONAL
    assert workspace.project_assignment_mode == ProjectAssignmentMode.AUTO_SILENT
    assert workspace.launch_status == LaunchStatus.PENDING
    assert workspace.data_sources == {"pack": {"total_runs": 1}}
    assert workspace.sandbox_config == {"filesystem_scope": ["/tmp"]}


def test_compact_data_source_entry_trims_result_summary_only():
    entry = compact_data_source_entry(
        {"last_result_summary": "x" * 12, "produces": ["docx"]},
        summary_limit=10,
    )
    untouched = compact_data_source_entry({"produces": ["docx"]}, summary_limit=10)

    assert entry == {"last_result_summary": "xxxxxxx...", "produces": ["docx"]}
    assert untouched == {"produces": ["docx"]}
