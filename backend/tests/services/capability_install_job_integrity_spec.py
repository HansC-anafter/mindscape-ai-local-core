from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.services import capability_install_jobs
from backend.app.services.capability_install_job_integrity import (
    attach_install_integrity_evidence,
    sha256_bytes,
    verify_file_upload_archive,
)
from backend.app.services.capability_install_jobs import CapabilityInstallJobService


class _CreateStore:
    def __init__(self):
        self.source_payload = None

    def create_job(self, *, install_id, source_kind, source_payload):
        self.source_payload = source_payload
        return {
            "install_id": install_id,
            "source_kind": source_kind,
            "source_payload": source_payload,
            "state": "queued",
        }


def test_file_upload_job_persists_archive_identity_and_source_commit(
    monkeypatch,
    tmp_path,
):
    jobs_root = tmp_path / "jobs"
    monkeypatch.setenv("MINDSCAPE_CAPABILITY_INSTALL_JOBS_DIR", str(jobs_root))
    monkeypatch.setattr(
        capability_install_jobs,
        "ensure_core_write_ready",
        lambda **_kwargs: None,
    )
    store = _CreateStore()
    content = b"canonical-mindpack-bytes"
    job = CapabilityInstallJobService(store=store).create_file_upload_job(
        filename="demo.mindpack",
        content=content,
        allow_overwrite=True,
        overwrite_review_confirmation="reviewed",
        profile_id="default-user",
        source_commit="abc123def",
    )

    source = store.source_payload
    assert source["archive_sha256"] == sha256_bytes(content)
    assert source["source_commit"] == "abc123def"
    assert Path(source["mindpack_path"]).read_bytes() == content
    assert verify_file_upload_archive(job) == {
        "status": "verified",
        "archive_sha256": sha256_bytes(content),
    }


def test_worker_fails_closed_when_durable_archive_changes(tmp_path):
    archive = tmp_path / "input.mindpack"
    archive.write_bytes(b"first")
    job = {
        "source_kind": "file_upload",
        "source_payload": {
            "mindpack_path": str(archive),
            "archive_sha256": sha256_bytes(b"first"),
        },
    }
    archive.write_bytes(b"mutated")

    with pytest.raises(ValueError, match="install_archive_sha256_mismatch"):
        verify_file_upload_archive(job)


def test_terminal_evidence_discloses_checksum_is_not_signature():
    payload = attach_install_integrity_evidence(
        job={
            "source_kind": "file_upload",
            "source_payload": {
                "archive_sha256": "a" * 64,
                "source_commit": "dec9d12a",
            },
        },
        result_payload={
            "capability_code": "comfyui_runtime",
            "activation": {"manifest_hash": "b" * 64},
        },
    )

    assert payload["install_integrity"] == {
        "schema_version": "mindscape.capability_install_integrity.v1",
        "trust_mode": "checksum_verified_not_signed",
        "archive_sha256": "a" * 64,
        "archive_verified_before_execution": True,
        "manifest_hash": "b" * 64,
        "source_commit": "dec9d12a",
        "signature_status": "not_available",
        "integrity_status": "verified",
    }


def test_legacy_queued_job_remains_executable_but_unverified():
    job = {
        "source_kind": "file_upload",
        "source_payload": {"mindpack_path": "/tmp/legacy.mindpack"},
    }
    assert verify_file_upload_archive(job) == {
        "status": "legacy_job_without_archive_sha256"
    }
