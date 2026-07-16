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
