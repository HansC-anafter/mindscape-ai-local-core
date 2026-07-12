"""Cold-start fail-closed source for the existing runner claim gate facade."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEFAULT_BOOTSTRAP_FILE = "/app/data/runtime/runner-claim-gate.paused"
MANAGED_BOOTSTRAP_SCHEMA_VERSION = 1
MANAGED_BOOTSTRAP_OWNER = "runner_claim_gate_facade"


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
        "ttl_seconds": payload.get("ttl_seconds"),
        "paused_at": str(payload.get("paused_at") or paused_at),
        "bootstrap_path": str(path),
        "schema_version": payload.get("schema_version"),
        "managed_by": payload.get("managed_by"),
    }


def write_managed_runner_claim_gate_bootstrap(
    payload: dict[str, Any] | None = None,
) -> bool:
    path = runner_claim_gate_bootstrap_path()
    source = payload if isinstance(payload, dict) else {}
    managed_payload = {
        "schema_version": MANAGED_BOOTSTRAP_SCHEMA_VERSION,
        "managed_by": MANAGED_BOOTSTRAP_OWNER,
        "reason": str(source.get("reason") or "maintenance"),
        "requested_by": str(source.get("requested_by") or "local_runtime"),
        "paused_at": str(
            source.get("paused_at") or datetime.now(timezone.utc).isoformat()
        ),
        "ttl_seconds": int(source.get("ttl_seconds") or 0),
    }
    temporary = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8") or "{}")
            if (
                not isinstance(existing, dict)
                or existing.get("schema_version")
                != MANAGED_BOOTSTRAP_SCHEMA_VERSION
                or existing.get("managed_by") != MANAGED_BOOTSTRAP_OWNER
            ):
                return False
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(managed_payload, handle, sort_keys=True, separators=(",", ":"))
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True
    except Exception:
        try:
            temporary.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def clear_managed_runner_claim_gate_bootstrap() -> tuple[bool, str | None]:
    path = runner_claim_gate_bootstrap_path()
    try:
        if not path.exists():
            return True, None
        payload = json.loads(path.read_text(encoding="utf-8") or "{}")
        if not isinstance(payload, dict):
            return False, "claim_gate_bootstrap_invalid"
        if (
            payload.get("schema_version") != MANAGED_BOOTSTRAP_SCHEMA_VERSION
            or payload.get("managed_by") != MANAGED_BOOTSTRAP_OWNER
        ):
            return False, "claim_gate_bootstrap_not_facade_managed"
        path.unlink()
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
        return True, None
    except Exception:
        return False, "claim_gate_bootstrap_clear_failed"
