from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend.app.services.runtime_database_incident_gate import (
    REQUIRED_SEARCHED_SOURCES,
    RESIDUAL_CLOSURE_MODE,
)


SCRIPT = (
    Path(__file__).resolve().parents[3]
    / "scripts/maintenance/postgres_incident_gate.py"
)
FIX_COMMIT = "0123456789abcdef0123456789abcdef01234567"
OWNER = "runtime-db-incident-owner"
RESTORE_ID = "restore-residual-cli-001"


def _run(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--journal-root", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_cli_records_bounded_exhaustion_and_closes_residual_gap(
    tmp_path: Path,
) -> None:
    opened = _run(
        tmp_path,
        "open",
        "postgres_server_closed_unexpectedly",
    )
    assert opened.returncode == 0
    incident_id = json.loads(opened.stdout)["incident_id"]
    ended_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    started_at = ended_at - timedelta(minutes=5)
    source_args = [
        value
        for source in sorted(REQUIRED_SEARCHED_SOURCES)
        for value in ("--searched-source", source)
    ]

    exhaustion = _run(
        tmp_path,
        "record-attribution-exhaustion",
        incident_id,
        "--search-started-at",
        started_at.isoformat(),
        "--search-ended-at",
        ended_at.isoformat(),
        *source_args,
        "--evidence-bundle-path",
        "evidence/attribution-exhaustion.json",
        "--evidence-bundle-sha256",
        "a" * 64,
        "--owner",
        OWNER,
        "--owner-authorization",
        "workspace-owner:bounded-attribution-convergence-and-close",
        "--owner-authorization-path",
        "evidence/owner-authorization.json",
        "--owner-authorization-sha256",
        "b" * 64,
    )
    assert exhaustion.returncode == 0, exhaustion.stderr
    event_path = next((tmp_path / "incidents").glob("*/events.jsonl"))
    exhaustion_event = next(
        event
        for event in (
            json.loads(line)
            for line in event_path.read_text(encoding="utf-8").splitlines()
        )
        if event["event"] == "attribution_exhaustion_recorded"
    )

    contained = _run(
        tmp_path,
        "contain",
        incident_id,
        "--permit-id",
        "containment-residual-cli-001",
        "--trigger-classification",
        "historical_event_irretrievable_after_bounded_search",
        "--fix-commit",
        FIX_COMMIT,
        "--allowed-operation-key",
        "backend_restart",
        "--test-evidence-path",
        "evidence/source-tests.json",
        "--test-evidence-path",
        "evidence/restore.json",
        "--restore-id",
        RESTORE_ID,
        "--expires-at",
        "2099-07-17T00:00:00Z",
        "--owner",
        OWNER,
    )
    assert contained.returncode == 0, contained.stderr
    contained_at = json.loads(contained.stdout)["updated_at"]
    common_args = (
        "--fix-commit",
        FIX_COMMIT,
        "--containment-evidence-path",
        "evidence/containment.json",
        "--containment-evidence-sha256",
        "c" * 64,
        "--test-evidence-path",
        "evidence/source-tests.json",
        "--test-evidence-path",
        "evidence/restore.json",
        "--test-evidence-sha256",
        "d" * 64,
        "--reproduction-evidence-path",
        "evidence/non-reproduction.json",
        "--reproduction-evidence-sha256",
        "e" * 64,
        "--soak-window",
        f"{contained_at}/{datetime.now(timezone.utc).isoformat()}",
        "--restore-id",
        RESTORE_ID,
        "--restore-evidence-path",
        "evidence/restore.json",
        "--restore-evidence-sha256",
        "f" * 64,
        "--resource-budget-evidence-path",
        "evidence/resource-budget.json",
        "--resource-budget-evidence-sha256",
        "1" * 64,
        "--owner",
        OWNER,
        "--owner-receipt-path",
        "evidence/owner-receipt.json",
        "--owner-receipt-sha256",
        "2" * 64,
    )

    closed = _run(
        tmp_path,
        "close-residual",
        incident_id,
        "--attribution-exhaustion-sha256",
        exhaustion_event["attribution_exhaustion_sha256"],
        *common_args,
    )

    assert closed.returncode == 0, closed.stderr
    payload = json.loads(closed.stdout)
    assert payload["state"] == "closed"
    assert payload["close_receipt"]["closure_mode"] == RESIDUAL_CLOSURE_MODE
