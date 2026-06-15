import json
from datetime import datetime, timezone
from types import SimpleNamespace

from backend.app.models.workspace import ArtifactType
from backend.app.services.stores.postgres.artifacts_projection import (
    build_artifact_filters,
    normalize_artifact_type,
    row_to_artifact,
)


def _deserialize_json(value, default=None):
    if not value:
        return default
    return json.loads(value)


def test_build_artifact_filters_keeps_db_level_filter_shape():
    where_clause, params = build_artifact_filters(
        workspace_id="workspace-1",
        playbook_code="demo",
        intent_id="intent-1",
        platform="ig.v1",
        kind="draft",
        artifact_types=["docx", "data"],
    )

    assert where_clause == (
        "workspace_id = :workspace_id AND playbook_code = :playbook_code "
        "AND intent_id = :intent_id AND metadata ~ :platform_regex "
        "AND metadata ~ :kind_regex AND artifact_type = ANY(:artifact_types)"
    )
    assert params["workspace_id"] == "workspace-1"
    assert params["platform_regex"] == '"platform"\\s*:\\s*"ig\\.v1"'
    assert params["kind_regex"] == '"kind"\\s*:\\s*"draft"'
    assert params["artifact_types"] == ["docx", "data"]


def test_row_to_artifact_projects_content_and_metadata():
    now = datetime(2026, 6, 16, 1, 0, tzinfo=timezone.utc)
    row = SimpleNamespace(
        id="artifact-1",
        workspace_id="workspace-1",
        intent_id="intent-1",
        task_id="task-1",
        execution_id="execution-1",
        thread_id="thread-1",
        playbook_code="demo",
        artifact_type="docx",
        title="Demo Artifact",
        summary=None,
        content=json.dumps({"body": "hello"}),
        storage_ref="file:///tmp/demo.docx",
        sync_state="pending",
        primary_action_type="download",
        metadata=json.dumps({"platform": "ig"}),
        created_at=now,
        updated_at=now,
    )

    artifact = row_to_artifact(row, deserialize_json=_deserialize_json)
    without_content = row_to_artifact(
        row,
        deserialize_json=_deserialize_json,
        include_content=False,
    )

    assert artifact.id == "artifact-1"
    assert artifact.summary == ""
    assert artifact.content == {"body": "hello"}
    assert artifact.metadata == {"platform": "ig"}
    assert without_content.content == {}


def test_normalize_artifact_type_accepts_enum_and_string():
    assert normalize_artifact_type(ArtifactType.DOCX) == "docx"
    assert normalize_artifact_type("data") == "data"
