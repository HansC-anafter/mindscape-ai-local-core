from app.routes.core.workspace_governance_core.serializers import (
    _build_artifact_landing_drilldown,
)


def test_artifact_landing_drilldown_reads_nested_landing_metadata(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "exec-1"
    artifact_dir.mkdir(parents=True)
    result_json_path = artifact_dir / "result.json"
    result_json_path.write_text('{"status":"ok"}', encoding="utf-8")

    drilldown = _build_artifact_landing_drilldown(
        {
            "landing": {
                "artifact_dir": str(artifact_dir),
                "result_json_path": str(result_json_path),
                "summary_md_path": str(artifact_dir / "summary.md"),
                "attachments_count": 0,
                "attachments": [],
                "landed_at": "2026-06-17T00:00:00+00:00",
            }
        }
    )

    assert drilldown is not None
    assert drilldown.artifact_dir == str(artifact_dir)
    assert drilldown.result_json_exists is True
    assert drilldown.summary_md_exists is False


def test_artifact_landing_drilldown_keeps_legacy_flat_metadata(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "exec-1"
    artifact_dir.mkdir(parents=True)
    result_json_path = artifact_dir / "result.json"
    summary_md_path = artifact_dir / "summary.md"
    result_json_path.write_text('{"status":"ok"}', encoding="utf-8")
    summary_md_path.write_text("# Summary", encoding="utf-8")

    drilldown = _build_artifact_landing_drilldown(
        {
            "landing_artifact_dir": str(artifact_dir),
            "landing_result_json_path": str(result_json_path),
            "landing_summary_md_path": str(summary_md_path),
            "landing_attachments_count": 0,
            "landing_attachments": [],
            "landing_landed_at": "2026-06-17T00:00:00+00:00",
        }
    )

    assert drilldown is not None
    assert drilldown.summary_md_exists is True
