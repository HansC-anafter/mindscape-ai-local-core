from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[3] / "scripts/maintenance/postgres_incident_gate.py"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--journal-root", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_exposes_stable_json_and_blocking_exit_code(tmp_path: Path) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    assert opened.returncode == 0
    incident_id = json.loads(opened.stdout)["incident_id"]

    evaluated = _run(tmp_path, "evaluate", "pack_install")
    assert evaluated.returncode == 2
    payload = json.loads(evaluated.stdout)
    assert payload["reason"] == "runtime_database_incident_open"
    assert payload["incident_id"] == incident_id


def test_cli_containment_requires_exact_artifact_operation_key(
    tmp_path: Path,
) -> None:
    opened = _run(tmp_path, "open", "postgres_server_closed_unexpectedly")
    incident_id = json.loads(opened.stdout)["incident_id"]
    artifact_sha256 = "a" * 64
    operation_key = f"capability_install_job@sha256:{artifact_sha256}"

    contained = _run(
        tmp_path,
        "contain",
        incident_id,
        "--permit-id",
        "containment-001",
        "--trigger-classification",
        "unattributed_backend_exit_under_structural_pressure",
        "--fix-commit",
        "0123456789abcdef",
        "--allowed-operation-key",
        operation_key,
        "--test-evidence-path",
        "evidence/source-tests.json",
        "--restore-id",
        "restore-preflight-001",
        "--expires-at",
        "2099-07-17T00:00:00Z",
        "--owner",
        "team-leads",
    )
    assert contained.returncode == 0

    allowed = _run(
        tmp_path,
        "evaluate",
        "capability_install_job:job-1",
        "--artifact-sha256",
        artifact_sha256,
    )
    blocked = _run(
        tmp_path,
        "evaluate",
        "capability_install_job:job-2",
        "--artifact-sha256",
        "b" * 64,
    )

    assert allowed.returncode == 0
    assert json.loads(allowed.stdout)["reason"] == "containment_repair_permit"
    assert blocked.returncode == 2
    assert json.loads(blocked.stdout)["reason"] == "runtime_database_incident_contained"
