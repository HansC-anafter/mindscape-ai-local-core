"""Cold-start fail-closed source for the existing runner claim gate facade."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_BOOTSTRAP_FILE = "/app/data/runtime/runner-claim-gate.paused"


def runner_claim_gate_bootstrap_path() -> Path:
    configured = os.getenv(
        "LOCAL_CORE_RUNNER_CLAIM_GATE_BOOTSTRAP_FILE",
        DEFAULT_BOOTSTRAP_FILE,
    )
    return Path(str(configured or DEFAULT_BOOTSTRAP_FILE).strip())


def read_runner_claim_gate_bootstrap() -> dict[str, Any] | None:
    path = runner_claim_gate_bootstrap_path()
    try:
        if not path.is_file():
            return None
        raw = path.read_text(encoding="utf-8").strip()
        payload = json.loads(raw) if raw else {}
        if not isinstance(payload, dict):
            payload = {}
        paused_at = datetime.fromtimestamp(
            path.stat().st_mtime,
            tz=timezone.utc,
        ).isoformat()
    except Exception:
        payload = {}
        paused_at = datetime.now(timezone.utc).isoformat()
    return {
        "state": "paused",
        "reason": str(payload.get("reason") or "cold_start_bootstrap"),
        "requested_by": str(payload.get("requested_by") or "local_runtime"),
        "paused_at": str(payload.get("paused_at") or paused_at),
        "bootstrap_path": str(path),
    }
