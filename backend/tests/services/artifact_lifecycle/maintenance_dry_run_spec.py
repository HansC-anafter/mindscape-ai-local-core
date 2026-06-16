import hashlib

import pytest

from app.services.artifact_lifecycle.maintenance import ArtifactLifecycleMaintenance
from app.services.artifact_lifecycle.policy import (
    ArtifactLifecycleCandidate,
    ArtifactLifecyclePolicy,
)
from app.services.result_object_contract import json_payload_sha256


class _Reader:
    def __init__(self, candidates):
        self.candidates = list(candidates)

    def iter_candidates(self, *, limit=None, page_size=200):
        candidates = self.candidates if limit is None else self.candidates[:limit]
        yield from candidates


class _Gate:
    def __init__(self, allowed):
        self.allowed = allowed

    def assert_apply_allowed(self):
        if not self.allowed:
            raise RuntimeError("apply blocked")


def _sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate(artifact_dir, *, status="succeeded", checksum=None):
    return ArtifactLifecycleCandidate(
        artifact_id="artifact-1",
        workspace_id="workspace-1",
        task_id="task-1",
        execution_id="exec-1",
        storage_ref=str(artifact_dir),
        result_json_path=str(artifact_dir / "result.json"),
        checksum_sha256=checksum,
        summary="artifact summary",
        manifest_summary="manifest summary",
        task_status=status,
    )


def test_maintenance_dry_run_classifies_without_deleting_summary(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "exec-1"
    artifact_dir.mkdir(parents=True)
    result_path = artifact_dir / "result.json"
    summary_path = artifact_dir / "summary.md"
    result_path.write_text('{"status":"ok"}', encoding="utf-8")
    summary_path.write_text("# Summary", encoding="utf-8")

    runner = ArtifactLifecycleMaintenance(
        reader=_Reader([_candidate(artifact_dir, checksum=_sha256(result_path))]),
        policy=ArtifactLifecyclePolicy(),
    )

    summary = runner.run(dry_run=True, limit=10)

    assert summary.as_dict()["examined"] == 1
    assert summary.as_dict()["remove_summary"] == 1
    assert summary_path.exists()


def test_maintenance_accepts_canonical_json_checksum_for_pretty_result_file(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "exec-1"
    artifact_dir.mkdir(parents=True)
    result_path = artifact_dir / "result.json"
    summary_path = artifact_dir / "summary.md"
    result_path.write_text('{\n  "status": "ok"\n}', encoding="utf-8")
    summary_path.write_text("# Summary", encoding="utf-8")
    runner = ArtifactLifecycleMaintenance(
        reader=_Reader(
            [
                _candidate(
                    artifact_dir,
                    checksum=json_payload_sha256({"status": "ok"}),
                )
            ]
        )
    )

    summary = runner.run(dry_run=True, limit=10)

    assert summary.remove_summary == 1
    assert "checksum-mismatch" not in summary.reasons


def test_maintenance_tracks_missing_result_and_active_task(tmp_path):
    missing_dir = tmp_path / "missing" / "exec-1"
    active_dir = tmp_path / "active" / "exec-2"
    missing_dir.mkdir(parents=True)
    active_dir.mkdir(parents=True)
    (missing_dir / "summary.md").write_text("# Summary", encoding="utf-8")
    (active_dir / "result.json").write_text('{"status":"ok"}', encoding="utf-8")
    (active_dir / "summary.md").write_text("# Summary", encoding="utf-8")

    runner = ArtifactLifecycleMaintenance(
        reader=_Reader(
            [
                _candidate(missing_dir),
                _candidate(active_dir, status="running"),
            ]
        )
    )

    summary = runner.run(dry_run=True, limit=10)

    assert summary.missing_result == 1
    assert summary.skipped_active == 1
    assert summary.remove_summary == 0


def test_maintenance_does_not_read_payload_when_summary_is_absent(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "exec-1"
    artifact_dir.mkdir(parents=True)
    runner = ArtifactLifecycleMaintenance(
        reader=_Reader([_candidate(artifact_dir)]),
    )

    summary = runner.run(dry_run=True, limit=10)

    assert summary.keep == 1
    assert summary.missing_result == 0
    assert summary.reasons == {"summary-missing": 1}


def test_maintenance_apply_requires_gate(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "exec-1"
    artifact_dir.mkdir(parents=True)
    result_path = artifact_dir / "result.json"
    result_path.write_text('{"status":"ok"}', encoding="utf-8")
    (artifact_dir / "summary.md").write_text("# Summary", encoding="utf-8")
    runner = ArtifactLifecycleMaintenance(
        reader=_Reader([_candidate(artifact_dir, checksum=_sha256(result_path))]),
        apply_gate=_Gate(False),
    )

    with pytest.raises(RuntimeError, match="apply blocked"):
        runner.run(
            dry_run=False,
            limit=10,
            archive_dir=tmp_path / "archives",
        )


def test_maintenance_apply_archives_before_unlinking_summary(tmp_path):
    artifact_dir = tmp_path / "artifacts" / "exec-1"
    artifact_dir.mkdir(parents=True)
    result_path = artifact_dir / "result.json"
    summary_path = artifact_dir / "summary.md"
    result_path.write_text('{"status":"ok"}', encoding="utf-8")
    summary_path.write_text("# Summary", encoding="utf-8")
    runner = ArtifactLifecycleMaintenance(
        reader=_Reader([_candidate(artifact_dir, checksum=_sha256(result_path))]),
        apply_gate=_Gate(True),
    )

    summary = runner.run(
        dry_run=False,
        limit=10,
        archive_dir=tmp_path / "archives",
    )

    assert summary.archived_summary == 1
    assert summary.archive_path is not None
    assert not summary_path.exists()
