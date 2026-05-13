import json
from types import SimpleNamespace

from backend.app.services.stores.postgres.workspaces_store import (
    PostgresWorkspacesStore,
)
from backend.app.services.task_result_landing import TaskResultLandingService


def _contains_key(value, target_key):
    if isinstance(value, dict):
        return target_key in value or any(
            _contains_key(child, target_key) for child in value.values()
        )
    if isinstance(value, list):
        return any(_contains_key(child, target_key) for child in value)
    return False


def test_build_task_result_payload_uses_landed_result_descriptor():
    payload = TaskResultLandingService._build_task_result_payload(
        existing_result={
            "execution_trace": {"events": ["stale"]},
            "last_error": "previous error",
        },
        incoming_result={
            "output": "done",
            "status": "completed",
            "execution_trace": {"events": [{"message": "x" * 1000} for _ in range(50)]},
        },
        summary="done",
        storage_ref="/workspace/artifacts/exec-1",
        execution_id="exec-1",
        artifact_id="artifact-1",
        landing_metadata={
            "result_json_path": "/workspace/artifacts/exec-1/result.json",
            "summary_md_path": "/workspace/artifacts/exec-1/summary.md",
        },
        deliverable_identity={
            "deliverable_name": "report",
            "deliverable_path": "report.md",
            "attachment_filenames": ["report.md"],
        },
        acceptance_evidence={"verified": True},
    )

    assert payload["summary"] == "done"
    assert payload["storage_ref"] == "/workspace/artifacts/exec-1"
    assert payload["execution_id"] == "exec-1"
    assert payload["artifact_id"] == "artifact-1"
    assert payload["result_object"]["bytes"] > 0
    assert (
        payload["result_object"]["result_json_path"]
        == "/workspace/artifacts/exec-1/result.json"
    )
    assert payload["deliverable_name"] == "report"
    assert payload["attachment_filenames"] == ["report.md"]
    assert payload["acceptance_evidence"] == {"verified": True}
    assert payload["last_error"] == "previous error"
    assert not _contains_key(payload, "execution_trace")


def test_get_landed_result_hydrates_full_result_json_from_storage(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "exec_001"
    artifact_dir.mkdir(parents=True)
    full_result = {
        "output": "done",
        "execution_trace": {
            "events": [{"message": "full trace retained in artifact storage"}],
        },
    }
    (artifact_dir / "result.json").write_text(
        json.dumps(full_result),
        encoding="utf-8",
    )

    class _ArtifactsStore:
        def get_by_execution_id(self, execution_id):
            return SimpleNamespace(
                id="artifact_001",
                storage_ref=str(artifact_dir),
                summary="done",
                content={"output": "descriptor summary"},
            )

    service = object.__new__(TaskResultLandingService)
    service._artifacts_store = _ArtifactsStore()
    service._tasks_store = SimpleNamespace()

    result = service.get_landed_result("exec_001")

    assert result["artifact_id"] == "artifact_001"
    assert result["result_json"] == full_result
    assert result["result_json"]["execution_trace"]["events"][0]["message"] == (
        "full trace retained in artifact storage"
    )


def test_extract_acceptance_evidence_derives_storyboard_preview_outputs():
    evidence = TaskResultLandingService._extract_acceptance_evidence(
        result_data={
            "outputs": {
                "session_id": "ds_001",
                "storyboard": {
                    "storyboard_id": "sb_001",
                    "workspace_id": "ws_001",
                    "scenes": [{"scene_id": "scene_01"}, {"scene_id": "scene_02"}],
                },
                "run_id": "run_001",
                "status": "completed",
                "timeline_items_synced": 2,
            }
        },
        result_json={},
        task=SimpleNamespace(pack_id="pd_execute_storyboard_preview", result={}),
    )

    assert evidence == {
        "evidence_kind": "storyboard_preview",
        "playbook_code": "pd_execute_storyboard_preview",
        "session_id": "ds_001",
        "storyboard": {
            "storyboard_id": "sb_001",
            "workspace_id": "ws_001",
            "scene_count": 2,
        },
        "storyboard_id": "sb_001",
        "run_id": "run_001",
        "status": "completed",
        "timeline_items_synced": 2,
    }


def test_extract_result_summary_compacts_nested_storyboard_payload():
    summary = TaskResultLandingService._extract_result_summary(
        {
            "steps": {
                "generate": {
                    "outputs": {
                        "payload": {
                            "storyboard": {
                                "storyboard_id": "sb_123",
                                "scenes": [{"scene_id": "s1"}, {"scene_id": "s2"}],
                                "raw": "x" * 5000,
                            },
                            "created_count": 2,
                        }
                    }
                }
            }
        }
    )

    assert "storyboard=storyboard_id=sb_123, scenes=2" in summary
    assert "created_count=2" in summary
    assert len(summary) <= 500
    assert "xxxxx" not in summary


def test_extract_result_summary_bounds_generic_nested_values():
    summary = TaskResultLandingService._extract_result_summary(
        {
            "steps": {
                "analyze": {
                    "outputs": {
                        "payload": {
                            "profile": {
                                "summary": "a" * 1000,
                                "score": 0.91,
                                "tags": ["one", "two"],
                            },
                            "items": list(range(20)),
                        }
                    }
                }
            }
        }
    )

    assert "score=0.91" in summary
    assert "items=list(count=20)" in summary
    assert len(summary) <= 500


def test_workspace_data_source_entry_compacts_last_result_summary():
    entry = PostgresWorkspacesStore._compact_data_source_entry(
        {
            "total_runs": 3,
            "last_result_summary": "x" * 700,
            "produces": [{"type": "artifact"}],
        }
    )

    assert entry["total_runs"] == 3
    assert entry["produces"] == [{"type": "artifact"}]
    assert len(entry["last_result_summary"]) == 500
    assert entry["last_result_summary"].endswith("...")
