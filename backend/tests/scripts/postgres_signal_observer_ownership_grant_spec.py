from __future__ import annotations

import hashlib
import json
import stat
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from backend.app.services.runtime_database_incident_gate import (
    RuntimeDatabaseIncidentJournal,
)
from scripts.maintenance import postgres_signal_observer_ownership_grant as grant_cli
from scripts.maintenance.postgres_signal_observer_preflight_core import (
    build_ownership_grant,
    build_ownership_request,
    materialize_ownership_grant,
)


REPO_ROOT = Path(__file__).resolve().parents[3]
MATERIALIZER = REPO_ROOT / "scripts/maintenance/postgres_signal_observer_ownership_grant.py"
REQUEST_MATERIALIZER = (
    REPO_ROOT / "scripts/maintenance/postgres_signal_observer_ownership_request.py"
)
INCIDENT_GATE = REPO_ROOT / "scripts/maintenance/postgres_incident_gate.py"
OWNER = "runtime-db-incident-owner"
ARTIFACT_SHA256 = "a" * 64


def _write_json(path: Path, payload: object) -> str:
    encoded = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def _receipt_chain(
    tmp_path: Path,
    *,
    incident_id: str = "postgres:test:incident",
) -> tuple[Path, Path, dict[str, object], str]:
    qualification = {
        "schema_version": "mindscape.postgres-signal-observer-qualification.v2",
        "phase": "qualification",
        "gate_pass": True,
        "first_failure": None,
        "failures": [],
        "scope": "postgres_signal_observer_only",
        "ownership_scope": "postgres_signal_observer_only",
        "owner": OWNER,
        "mutation_permit": False,
        "quiet_window_owned": False,
        "incident_id": incident_id,
        "artifact_sha256": ARTIFACT_SHA256,
        "checks": {
            "diagnostic_permit_admission": {
                "schema_version": "mindscape.postgres-signal-observer-permit-admission.v1",
                "allowed": True,
                "failure_code": None,
                "incident_id": incident_id,
                "state": "open_unattributed",
                "conflicting_permit": False,
                "payload_persisted": False,
            }
        },
    }
    qualification_path = tmp_path / "qualification.json"
    qualification_sha256 = _write_json(qualification_path, qualification)
    now = datetime.now(timezone.utc)
    request = build_ownership_request(
        qualification,
        qualification_receipt_sha256=qualification_sha256,
        exact_operation=f"postgres_signal_observer_start@sha256:{ARTIFACT_SHA256}",
        issued_at=now.isoformat(),
        expires_at=(now + timedelta(minutes=10)).isoformat(),
        requested_owner=OWNER,
    )
    request_path = tmp_path / "ownership-request.json"
    request_sha256 = _write_json(request_path, request)
    return qualification_path, request_path, request, request_sha256


def _run_materializer(
    request_path: Path,
    output_path: Path,
    *extra: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(MATERIALIZER),
            "--ownership-request-receipt",
            str(request_path),
            "--granted-owner",
            OWNER,
            "--output-json",
            str(output_path),
            *extra,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def _run_request_materializer(
    qualification_path: Path,
    output_path: Path,
) -> subprocess.CompletedProcess[str]:
    now = datetime.now(timezone.utc)
    return subprocess.run(
        [
            sys.executable,
            str(REQUEST_MATERIALIZER),
            "--qualification-receipt",
            str(qualification_path),
            "--exact-operation",
            f"postgres_signal_observer_start@sha256:{ARTIFACT_SHA256}",
            "--issued-at",
            now.isoformat(),
            "--expires-at",
            (now + timedelta(minutes=10)).isoformat(),
            "--requested-owner",
            OWNER,
            "--output-json",
            str(output_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_request_cli_materializes_live_capture_scope(tmp_path: Path) -> None:
    qualification_path, _request_path, _request, _request_sha = _receipt_chain(
        tmp_path
    )
    output_path = tmp_path / "cli-ownership-request.json"

    completed = _run_request_materializer(qualification_path, output_path)

    assert completed.returncode == 0
    request = json.loads(output_path.read_text(encoding="utf-8"))
    assert request["capture_context"] == "live_runtime"
    assert "bounded live PostgreSQL signal observer" in request["scope"]
    assert "isolated" not in request["scope"].lower()
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600


def _run_diagnose(
    tmp_path: Path,
    *,
    qualification_path: Path,
    request_path: Path,
    grant_path: Path,
    expires_at: str,
    permit_id: str,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(INCIDENT_GATE),
            "--journal-root",
            str(tmp_path / "journal"),
            "diagnose",
            "--qualification-receipt",
            str(qualification_path),
            "--ownership-request-receipt",
            str(request_path),
            "--ownership-grant-receipt",
            str(grant_path),
            "--permit-id",
            permit_id,
            "--source-commit",
            "0123456789abcdef",
            "--diagnostic-operation",
            "postgres_signal_observer_start",
            "--artifact-sha256",
            ARTIFACT_SHA256,
            "--test-evidence-path",
            "evidence/materializer-tests.json",
        "--capture-evidence-id",
        "materializer-live-capture",
            "--budget-sha256",
            "b" * 64,
            "--expires-at",
            expires_at,
            "--owner",
            OWNER,
        ],
        check=False,
        capture_output=True,
        text=True,
    )


def test_materializer_builds_the_exact_request_bound_grant(tmp_path: Path) -> None:
    _qualification_path, request_path, request, request_sha256 = _receipt_chain(tmp_path)

    grant = materialize_ownership_grant(request_path, granted_owner=OWNER)

    assert grant == build_ownership_grant(
        request,
        ownership_request_receipt_sha256=request_sha256,
        granted_owner=OWNER,
    )
    assert grant["ownership_request_receipt_sha256"] == request_sha256
    assert grant["explicit_exclusions"] == [
        "live_postgresql_mutation",
        "live_pgbouncer_mutation",
        "runner_mutation",
        "backend_mutation",
        "control_mutation",
        "frontend_mutation",
        "reload_restart_config",
        "queue_pool_capacity",
        "v52_media_model",
    ]
    assert grant["capture_context"] == "live_runtime"
    assert "isolated" not in str(grant["scope"]).lower()
    assert "execution_frontier" not in grant["explicit_exclusions"]
    assert "v52_media_model_heavy_cpu" not in grant["explicit_exclusions"]


def test_cli_writes_one_owner_only_exact_grant(tmp_path: Path) -> None:
    _qualification_path, request_path, request, request_sha256 = _receipt_chain(tmp_path)
    output_path = tmp_path / "grant.json"

    completed = _run_materializer(request_path, output_path)

    assert completed.returncode == 0
    expected = build_ownership_grant(
        request,
        ownership_request_receipt_sha256=request_sha256,
        granted_owner=OWNER,
    )
    assert json.loads(output_path.read_text(encoding="utf-8")) == expected
    assert json.loads(completed.stdout) == expected
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600


@pytest.mark.parametrize(
    "extra",
    (
        ("--incident-id", "postgres:forged"),
        ("--artifact-sha256", ARTIFACT_SHA256),
        ("--exact-operation", "postgres_signal_observer_start"),
        ("--scope", "forged"),
        ("--explicit-exclusion", "execution_frontier"),
    ),
)
def test_cli_rejects_caller_owned_grant_fields(
    tmp_path: Path,
    extra: tuple[str, str],
) -> None:
    _qualification_path, request_path, _request, _sha = _receipt_chain(tmp_path)
    output_path = tmp_path / "grant.json"

    completed = _run_materializer(request_path, output_path, *extra)

    assert completed.returncode == 2
    assert "unrecognized arguments" in completed.stderr
    assert not output_path.exists()


def test_cli_never_overwrites_an_existing_output(tmp_path: Path) -> None:
    _qualification_path, request_path, _request, _sha = _receipt_chain(tmp_path)
    output_path = tmp_path / "grant.json"
    output_path.write_text("foreign-owner\n", encoding="utf-8")

    completed = _run_materializer(request_path, output_path)

    assert completed.returncode != 0
    assert "ownership_grant_output_unavailable" in completed.stderr
    assert output_path.read_text(encoding="utf-8") == "foreign-owner\n"


def test_cli_never_follows_or_overwrites_an_output_symlink(tmp_path: Path) -> None:
    _qualification_path, request_path, _request, _sha = _receipt_chain(tmp_path)
    foreign = tmp_path / "foreign.json"
    foreign.write_text("foreign-owner\n", encoding="utf-8")
    output_path = tmp_path / "grant.json"
    output_path.symlink_to(foreign)

    completed = _run_materializer(request_path, output_path)

    assert completed.returncode != 0
    assert "ownership_grant_output_unavailable" in completed.stderr
    assert output_path.is_symlink()
    assert foreign.read_text(encoding="utf-8") == "foreign-owner\n"


def test_writer_removes_owned_staging_after_fsync_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "grant.json"

    def fail_fsync(_descriptor: int) -> None:
        raise OSError("fsync failed")

    monkeypatch.setattr(grant_cli.os, "fsync", fail_fsync)

    with pytest.raises(ValueError, match="ownership_grant_output_unavailable"):
        grant_cli._write_exclusive_json(output_path, {"state": "granted"})

    assert not output_path.exists()
    assert list(tmp_path.glob(".*.tmp")) == []


def test_writer_preserves_foreign_replacement_and_reports_incomplete_cleanup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "grant.json"
    replacement = b"foreign-owner\n"

    def replace_staging_then_fail(_descriptor: int) -> None:
        temporary = next(tmp_path.glob(".*.tmp"))
        temporary.unlink()
        temporary.write_bytes(replacement)
        raise OSError("fsync failed after replacement")

    monkeypatch.setattr(grant_cli.os, "fsync", replace_staging_then_fail)

    with pytest.raises(
        ValueError,
        match="ownership_grant_output_cleanup_incomplete",
    ):
        grant_cli._write_exclusive_json(output_path, {"state": "granted"})

    assert not output_path.exists()
    remaining = list(tmp_path.glob(".*.tmp"))
    assert len(remaining) == 1
    assert remaining[0].read_bytes() == replacement


def test_writer_reports_unlink_failure_without_claiming_output_absence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_path = tmp_path / "grant.json"
    original_unlink = Path.unlink

    def fail_owned_unlink(path: Path, *args, **kwargs) -> None:
        if path.name.startswith(".grant.json.") or path == output_path:
            raise OSError("unlink failed")
        original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_owned_unlink)

    with pytest.raises(
        ValueError,
        match="ownership_grant_output_cleanup_incomplete",
    ):
        grant_cli._write_exclusive_json(output_path, {"state": "granted"})

    assert output_path.exists()
    assert len(list(tmp_path.glob(".*.tmp"))) == 1


@pytest.mark.parametrize(
    ("mutation", "failure"),
    (
        ("missing", "diagnostic_receipt_unavailable"),
        ("malformed", "diagnostic_receipt_unavailable"),
        ("owner", "ownership_granted_owner_mismatch"),
        ("scope", "ownership_scope_invalid"),
        ("exclusions", "ownership_exclusions_invalid"),
    ),
)
def test_cli_rejects_unusable_or_changed_request_without_output(
    tmp_path: Path,
    mutation: str,
    failure: str,
) -> None:
    _qualification_path, request_path, request, _sha = _receipt_chain(tmp_path)
    if mutation == "missing":
        request_path.unlink()
    elif mutation == "malformed":
        request_path.write_text("not-json\n", encoding="utf-8")
    elif mutation == "owner":
        request["requested_owner"] = "forged-owner"
        _write_json(request_path, request)
    elif mutation == "scope":
        request["scope"] = "forged-scope"
        _write_json(request_path, request)
    else:
        request["explicit_exclusions"] = ["live_postgresql_mutation"]
        _write_json(request_path, request)
    output_path = tmp_path / "grant.json"

    completed = _run_materializer(request_path, output_path)

    assert completed.returncode != 0
    assert not output_path.exists()
    assert failure in completed.stderr


def test_materialized_grant_records_one_exact_observer_permit(tmp_path: Path) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path / "journal")
    incident_id = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly"
    ).incident_id
    qualification_path, request_path, request, _request_sha = _receipt_chain(
        tmp_path,
        incident_id=incident_id,
    )
    grant_path = tmp_path / "grant.json"
    materialized = _run_materializer(request_path, grant_path)
    assert materialized.returncode == 0

    diagnosed = _run_diagnose(
        tmp_path,
        qualification_path=qualification_path,
        request_path=request_path,
        grant_path=grant_path,
        expires_at=str(request["expires_at"]),
        permit_id="observer-materializer-permit",
    )

    assert diagnosed.returncode == 0
    current = journal.current()
    assert current is not None
    assert current.diagnostic_permit is not None
    assert current.diagnostic_permit["permit_id"] == "observer-materializer-permit"
    assert current.diagnostic_permit["allowed_operation_keys"] == [
        f"postgres_signal_observer_start@sha256:{ARTIFACT_SHA256}"
    ]


def test_manual_exclusions_mismatch_is_rejected_before_permit_write(
    tmp_path: Path,
) -> None:
    journal = RuntimeDatabaseIncidentJournal(tmp_path / "journal")
    incident_id = journal.open_incident(
        failure_code="postgres_server_closed_unexpectedly"
    ).incident_id
    qualification_path, request_path, request, _request_sha = _receipt_chain(
        tmp_path,
        incident_id=incident_id,
    )
    grant_path = tmp_path / "grant.json"
    assert _run_materializer(request_path, grant_path).returncode == 0
    grant = json.loads(grant_path.read_text(encoding="utf-8"))
    grant["explicit_exclusions"].append("execution_frontier")
    _write_json(grant_path, grant)

    diagnosed = _run_diagnose(
        tmp_path,
        qualification_path=qualification_path,
        request_path=request_path,
        grant_path=grant_path,
        expires_at=str(request["expires_at"]),
        permit_id="observer-mismatched-grant",
    )

    assert diagnosed.returncode != 0
    assert "ownership_grant_receipt_invalid" in diagnosed.stderr
    current = journal.current()
    assert current is not None
    assert current.diagnostic_permit is None
