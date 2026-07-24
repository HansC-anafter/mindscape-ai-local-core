from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from backend.app.routes.core.capability_install_core.install_commit_coordinator import (
    PackBackoutReceipt,
    validate_candidate_version,
)
from backend.app.services import pack_install_version_preflight


def _validate(incoming_version: str, incoming_hash: str, **kwargs):
    return validate_candidate_version(
        incoming_version=incoming_version,
        incoming_hash=incoming_hash,
        committed_version="2.0.0",
        committed_hash="hash-2",
        committed_install_id="install-2",
        live_version="2.0.0",
        live_hash="hash-2",
        **kwargs,
    )


def test_upgrade_and_same_hash_idempotency_are_allowed() -> None:
    assert _validate("2.1.0", "hash-21") == "upgrade"
    assert _validate("2.0.0", "hash-2") == "idempotent"


def test_same_version_different_hash_and_normal_downgrade_are_rejected() -> None:
    with pytest.raises(RuntimeError, match="different_hash"):
        _validate("2.0.0", "other")
    with pytest.raises(RuntimeError, match="explicit_backout"):
        _validate("1.9.0", "hash-19")


def test_downgrade_requires_exact_backout_artifact_and_schema_receipt() -> None:
    receipt = PackBackoutReceipt(
        backout_from_install_id="install-2",
        artifact_sha256="hash-19",
        target_version="1.9.0",
        schema_compatibility_receipt="schema-compatible-1",
        owner_approval="team-leads",
    )
    assert (
        _validate("1.9.0", "hash-19", backout_receipt=receipt)
        == "authorized_backout"
    )


def test_backout_source_must_match_latest_committed_install() -> None:
    receipt = PackBackoutReceipt(
        backout_from_install_id="install-other",
        artifact_sha256="hash-19",
        target_version="1.9.0",
        schema_compatibility_receipt="schema-compatible-1",
        owner_approval="team-leads",
    )

    with pytest.raises(RuntimeError, match="source_install_id_mismatch"):
        _validate("1.9.0", "hash-19", backout_receipt=receipt)


def test_split_live_truth_blocks_before_candidate_prepare() -> None:
    with pytest.raises(RuntimeError, match="does_not_match"):
        validate_candidate_version(
            incoming_version="2.1.0",
            incoming_hash="hash-21",
            committed_version="2.0.0",
            committed_hash="hash-2",
            live_version="1.9.0",
            live_hash="hash-19",
        )


class _TruthReader:
    def __init__(self, receipt, bootstrap_receipt=None):
        self.receipt = receipt
        self.bootstrap_receipt = bootstrap_receipt

    def latest_commit(self, _pack_id):
        return self.receipt

    def bootstrap_legacy_commit(self, **_kwargs):
        return self.bootstrap_receipt


def _manifest(path: Path, version: str) -> str:
    path.write_text(f"code: demo\nversion: {version}\n", encoding="utf-8")
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_receipt_bound_preflight_accepts_upgrade_before_side_effects(
    tmp_path: Path,
    monkeypatch,
) -> None:
    live = tmp_path / "live.yaml"
    candidate = tmp_path / "candidate.yaml"
    live_hash = _manifest(live, "2.0.0")
    _manifest(candidate, "2.1.0")
    monkeypatch.setattr(
        pack_install_version_preflight,
        "record_database_failure",
        lambda *_args, **_kwargs: None,
    )

    decision = pack_install_version_preflight.validate_existing_pack_version_truth(
        capability_code="demo",
        candidate_manifest_path=candidate,
        live_manifest_path=live,
        artifact_sha256="a" * 64,
        truth_reader=_TruthReader(
            {
                "install_id": "install-2",
                "version": "2.0.0",
                "manifest_hash": live_hash,
            }
        ),
    )

    assert decision == "upgrade"


def test_unreceipted_existing_pack_opens_incident_and_stops(tmp_path: Path, monkeypatch) -> None:
    live = tmp_path / "live.yaml"
    candidate = tmp_path / "candidate.yaml"
    _manifest(live, "2.0.0")
    _manifest(candidate, "2.1.0")
    failures = []
    monkeypatch.setattr(
        pack_install_version_preflight,
        "record_database_failure",
        lambda code, **_kwargs: failures.append(code),
    )

    with pytest.raises(RuntimeError, match="committed_receipt_missing"):
        pack_install_version_preflight.validate_existing_pack_version_truth(
            capability_code="demo",
            candidate_manifest_path=candidate,
            live_manifest_path=live,
            artifact_sha256="a" * 64,
            truth_reader=_TruthReader(None),
        )

    assert failures == ["pack_committed_receipt_missing"]


def test_verified_legacy_receipt_bootstrap_allows_upgrade(tmp_path: Path, monkeypatch):
    live = tmp_path / "live.yaml"
    candidate = tmp_path / "candidate.yaml"
    live_hash = _manifest(live, "2.0.0")
    _manifest(candidate, "2.1.0")
    monkeypatch.setattr(
        pack_install_version_preflight,
        "record_database_failure",
        lambda *_args, **_kwargs: None,
    )

    decision = pack_install_version_preflight.validate_existing_pack_version_truth(
        capability_code="demo",
        candidate_manifest_path=candidate,
        live_manifest_path=live,
        artifact_sha256="a" * 64,
        truth_reader=_TruthReader(
            None,
            {
                "install_id": "install-2",
                "version": "2.0.0",
                "manifest_hash": live_hash,
            },
        ),
    )

    assert decision == "upgrade"


def test_legacy_bootstrap_requires_matching_job_activation_and_live_truth():
    manifest_hash = "a" * 64
    row = {
        "pack_id": "demo",
        "enabled": True,
        "installed_metadata": {"install_id": "install-1", "version": "2.0.0"},
        "install_id": "install-1",
        "job_state": "succeeded",
        "source_payload": {"archive_sha256": "b" * 64},
        "result_payload": {
            "version": "2.0.0",
            "activation": {"manifest_hash": manifest_hash},
            "install_integrity": {"manifest_hash": manifest_hash},
        },
        "activation_manifest_hash": manifest_hash,
        "finished_at": "2026-07-16T17:55:15Z",
    }

    receipt = pack_install_version_preflight._validated_legacy_bootstrap(
        row,
        pack_id="demo",
        live_version="2.0.0",
        live_manifest_hash=manifest_hash,
    )
    assert receipt["install_id"] == "install-1"
    assert receipt["artifact_sha256"] == "b" * 64

    row["activation_manifest_hash"] = "c" * 64
    with pytest.raises(RuntimeError, match="manifest_hashes"):
        pack_install_version_preflight._validated_legacy_bootstrap(
            row,
            pack_id="demo",
            live_version="2.0.0",
            live_manifest_hash=manifest_hash,
        )


def test_legacy_bootstrap_casts_text_installed_metadata_before_json_access():
    source = Path(pack_install_version_preflight.__file__).read_text(encoding="utf-8")

    assert "CAST(installed.metadata AS JSONB) AS installed_metadata" in source
    assert "CAST(installed.metadata AS JSONB) ->> 'install_id'" in source


def test_legacy_bootstrap_hashes_same_install_retained_artifact(tmp_path: Path):
    install_id = "install-1"
    artifact = (
        tmp_path
        / "capability-install-jobs"
        / install_id
        / "input.mindpack"
    )
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"legacy artifact")

    observed = pack_install_version_preflight._retained_legacy_artifact_sha256(
        {"mindpack_path": str(artifact)},
        install_id=install_id,
    )

    assert observed == hashlib.sha256(b"legacy artifact").hexdigest()


def test_legacy_bootstrap_rejects_retained_artifact_from_other_install(
    tmp_path: Path,
):
    artifact = (
        tmp_path
        / "capability-install-jobs"
        / "install-other"
        / "input.mindpack"
    )
    artifact.parent.mkdir(parents=True)
    artifact.write_bytes(b"other artifact")

    observed = pack_install_version_preflight._retained_legacy_artifact_sha256(
        {"mindpack_path": str(artifact)},
        install_id="install-1",
    )

    assert observed == ""
