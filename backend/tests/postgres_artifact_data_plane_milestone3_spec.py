import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from backend.app.services.result_object_contract import (
    analysis_result_object_key,
    json_payload_size,
)
from backend.app.services.stores.postgres.artifacts_store import PostgresArtifactsStore
from backend.app.services.task_result_landing import TaskResultLandingService


def _backend_root():
    return Path(__file__).resolve().parents[1]


class _FakeArtifactsStore:
    def __init__(self):
        self.created = []
        self.updated = []

    def get_by_execution_id(self, execution_id):
        return None

    def create_artifact(self, artifact):
        self.created.append(artifact)
        return artifact

    def update_artifact(self, artifact_id, **kwargs):
        self.updated.append((artifact_id, kwargs))
        return True


class _FakeManifestStore:
    def __init__(self):
        self.manifests = []

    def upsert_result_manifest(self, **kwargs):
        self.manifests.append(kwargs)
        return kwargs


class _FakeTasksStore:
    def __init__(self):
        self.updated = []
        self.partial_updates = []
        self.task = SimpleNamespace(
            id="task-001",
            result={},
            execution_context={},
            params={},
            project_id="project-001",
            pack_id=None,
            created_at=None,
            started_at=None,
        )

    def get_task(self, task_id):
        return self.task if task_id == "task-001" else None

    def get_task_by_execution_id(self, execution_id):
        return self.task

    def update_task_status(self, **kwargs):
        self.updated.append(kwargs)
        return True

    def update_task(self, task_id, **kwargs):
        self.partial_updates.append((task_id, kwargs))
        return True


def test_milestone3_migration_defines_pointer_only_data_plane_tables():
    migration_source = (
        _backend_root()
        / "alembic_migrations/postgres/versions/"
        "20260514123000_add_artifact_manifest_media_data_plane.py"
    ).read_text(encoding="utf-8")

    for table_name in (
        "artifact_manifest",
        "media_assets",
        "media_objects",
        "asset_gallery_projection",
        "artifact_search_index",
    ):
        assert f'"{table_name}"' in migration_source

    assert 'sa.Column("content"' not in migration_source
    assert "object_key" in migration_source
    assert "checksum_sha256" in migration_source
    upgrade_source = migration_source.split("def downgrade", maxsplit=1)[0]
    assert "drop_table" not in upgrade_source


def test_task_result_landing_writes_manifest_and_bounded_artifact_content(tmp_path):
    service = object.__new__(TaskResultLandingService)
    service._tasks_store = _FakeTasksStore()
    service._artifacts_store = _FakeArtifactsStore()
    service._artifact_manifest_store = _FakeManifestStore()

    result_data = {
        "output": "done",
        "status": "completed",
        "execution_trace": {
            "events": [{"message": "x" * 1000} for _ in range(50)]
        },
    }

    landed = service._do_land(
        workspace_id="workspace-001",
        execution_id="exec-001",
        result_data=result_data,
        storage_base_path=str(tmp_path),
        artifacts_dirname="artifacts",
        thread_id="thread-001",
        project_id="project-001",
        task_id="task-001",
    )

    assert landed.artifact_id is not None
    artifact = service._artifacts_store.created[0]
    assert "execution_trace" not in json.dumps(artifact.content)
    assert artifact.content["result_object"]["object_key"] == (
        "analysis_result/exec-001.json"
    )
    assert json_payload_size(artifact.content) < 16 * 1024

    manifest = service._artifact_manifest_store.manifests[0]
    assert manifest["workspace_id"] == "workspace-001"
    assert manifest["task_id"] == "task-001"
    assert manifest["execution_id"] == "exec-001"
    assert manifest["result_descriptor"]["result_object"]["object_key"] == (
        "analysis_result/exec-001.json"
    )
    assert manifest["result_descriptor"]["result_object"]["bytes"] == (
        json_payload_size(result_data)
    )

    task_result = service._tasks_store.updated[0]["result"]
    assert task_result["result_object"]["object_key"] == "analysis_result/exec-001.json"
    assert "execution_trace" not in json.dumps(task_result)
    assert (tmp_path / "artifacts" / "exec-001" / "result.json").exists()


def test_task_result_landing_can_defer_terminal_status_until_governance_finishes(
    tmp_path,
):
    service = object.__new__(TaskResultLandingService)
    service._tasks_store = _FakeTasksStore()
    service._artifacts_store = _FakeArtifactsStore()
    service._artifact_manifest_store = _FakeManifestStore()

    service._do_land(
        workspace_id="workspace-001",
        execution_id="exec-deferred",
        result_data={"output": "done", "status": "completed"},
        storage_base_path=str(tmp_path),
        artifacts_dirname="artifacts",
        thread_id="thread-001",
        project_id="project-001",
        task_id="task-001",
        defer_task_terminal_update=True,
    )

    assert service._tasks_store.updated == []
    assert len(service._tasks_store.partial_updates) == 1
    task_id, payload = service._tasks_store.partial_updates[0]
    assert task_id == "task-001"
    assert "status" not in payload
    assert payload["result"]["execution_id"] == "exec-deferred"


def test_artifact_store_rejects_unbounded_content_and_metadata():
    store = object.__new__(PostgresArtifactsStore)

    with pytest.raises(ValueError, match="artifact content exceeds"):
        store._assert_artifact_payload_budget(
            content={"raw": "x" * (16 * 1024)},
            metadata={},
        )

    with pytest.raises(ValueError, match="artifact metadata exceeds"):
        store._assert_artifact_payload_budget(
            content={},
            metadata={"raw": "x" * (64 * 1024)},
        )


def test_analysis_result_object_key_sanitizes_path_segments():
    assert analysis_result_object_key("../run/001") == "analysis_result/run_001.json"
