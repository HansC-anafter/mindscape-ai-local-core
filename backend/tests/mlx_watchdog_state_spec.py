from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "mlx-server"
    / "watchdog_state.py"
)


def test_watchdog_state_accepts_iso8601_active_payload(tmp_path) -> None:
    now = time.time()
    state_file = tmp_path / "runner_decision_synthesis_35b.json"
    payload = {
        "status": "active",
        "phase": "generating",
        "request_id": "dar_test",
        "workspace_id": "ws_test",
        "reference_id": "ref_test",
        "model_lane_id": "runner:decision_synthesis_35b",
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 30)),
        "heartbeat_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 5)),
    }
    state_file.write_text(json.dumps(payload), encoding="utf-8")

    result = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--state-file",
            str(state_file),
            "--hard-timeout",
            "7200",
            "--heartbeat-timeout",
            "120",
            "--now",
            str(now),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "active phase=generating" in result.stdout
