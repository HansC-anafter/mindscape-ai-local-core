from datetime import datetime, timezone

from app.services.artifact_lifecycle.summary_sidecar import (
    build_summary_markdown,
    resolve_landing_metadata,
    should_write_eager_summary,
    summary_path_for_candidate,
)


def test_summary_sidecar_mode_defaults_to_lazy(monkeypatch):
    monkeypatch.delenv("ARTIFACT_SUMMARY_SIDECAR_MODE", raising=False)

    assert should_write_eager_summary() is False


def test_summary_sidecar_mode_supports_eager_rollback(monkeypatch):
    monkeypatch.setenv("ARTIFACT_SUMMARY_SIDECAR_MODE", "eager")

    assert should_write_eager_summary() is True


def test_build_summary_markdown_matches_landing_shape():
    markdown = build_summary_markdown(
        execution_id="exec-1",
        workspace_id="workspace-1",
        task_id="task-1",
        thread_id=None,
        project_id="project-1",
        summary="done",
        landed_at=datetime(2026, 6, 17, tzinfo=timezone.utc),
    )

    assert "# Execution exec-1" in markdown
    assert "- workspace_id: workspace-1" in markdown
    assert "- thread_id: (none)" in markdown
    assert "done" in markdown


def test_resolve_landing_metadata_supports_nested_and_legacy_flat_shapes():
    nested = resolve_landing_metadata(
        {
            "landing": {
                "artifact_dir": "/tmp/artifacts/exec-1",
                "result_json_path": "/tmp/artifacts/exec-1/result.json",
                "summary_md_path": "/tmp/artifacts/exec-1/summary.md",
                "attachments_count": 1,
                "attachments": ["/tmp/artifacts/exec-1/attachments/a.txt"],
                "landed_at": "2026-06-17T00:00:00+00:00",
            }
        }
    )
    legacy = resolve_landing_metadata(
        {
            "landing_artifact_dir": "/tmp/artifacts/exec-2",
            "landing_result_json_path": "/tmp/artifacts/exec-2/result.json",
            "landing_summary_md_path": "/tmp/artifacts/exec-2/summary.md",
            "landing_attachments_count": 0,
            "landing_attachments": [],
            "landing_landed_at": "2026-06-17T00:00:01+00:00",
        }
    )

    assert nested["summary_md_path"] == "/tmp/artifacts/exec-1/summary.md"
    assert nested["attachments_count"] == 1
    assert legacy["result_json_path"] == "/tmp/artifacts/exec-2/result.json"
    assert legacy["landed_at"] == "2026-06-17T00:00:01+00:00"


def test_summary_path_prefers_landing_metadata_over_storage_ref():
    path = summary_path_for_candidate(
        "/tmp/storage/exec-1",
        {"landing": {"summary_md_path": "/tmp/landing/exec-1/summary.md"}},
    )

    assert str(path) == "/tmp/landing/exec-1/summary.md"
