"""Bounded file-backed state for the Remote Workbench bridge."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping


def utc_now() -> str:
    """Return a stable UTC timestamp for persisted bridge evidence."""

    return datetime.now(timezone.utc).isoformat()


class BridgeStateStore:
    """Persist supervisor status and maintenance state without database writes."""

    def __init__(
        self,
        *,
        status_path: Path,
        events_path: Path,
        maintenance_path: Path,
        event_log_max_bytes: int,
    ) -> None:
        self.status_path = status_path
        self.events_path = events_path
        self.maintenance_path = maintenance_path
        self.event_log_max_bytes = event_log_max_bytes

    def ensure_directory(self) -> None:
        """Create the state directory with operator-only permissions."""

        if self.status_path.parent.is_symlink():
            raise RuntimeError("Bridge state directory must not be a symbolic link")
        self.status_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.status_path.parent, 0o700)

    def _write_json(self, path: Path, payload: Mapping[str, Any]) -> None:
        self.ensure_directory()
        descriptor, temporary_value = tempfile.mkstemp(
            prefix=f".{path.name}.",
            dir=path.parent,
        )
        temporary = Path(temporary_value)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, sort_keys=True, separators=(",", ":"))
                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
            os.chmod(path, 0o600)
        finally:
            if temporary.exists():
                temporary.unlink()

    def write_status(self, payload: Mapping[str, Any]) -> None:
        """Atomically replace the current status projection."""

        self._write_json(self.status_path, payload)

    def read_status(self) -> dict[str, Any] | None:
        """Read the current status projection when it is valid JSON."""

        try:
            value = json.loads(self.status_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return value if isinstance(value, dict) else None

    def append_event(self, payload: Mapping[str, Any]) -> None:
        """Append one bounded event record without storing credentials."""

        self.ensure_directory()
        if self.events_path.exists() and self.events_path.stat().st_size >= self.event_log_max_bytes:
            rotated = self.events_path.with_suffix(".jsonl.previous")
            if rotated.exists():
                rotated.unlink()
            os.replace(self.events_path, rotated)
            os.chmod(rotated, 0o600)
        descriptor = os.open(
            self.events_path,
            os.O_WRONLY | os.O_APPEND | os.O_CREAT,
            0o600,
        )
        with os.fdopen(descriptor, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
            handle.write("\n")
        os.chmod(self.events_path, 0o600)

    def maintenance(self) -> dict[str, Any]:
        """Return a fail-safe maintenance projection."""

        if self.maintenance_path.is_symlink():
            return {"enabled": True, "reason": "maintenance_state_symlink"}
        try:
            payload = json.loads(self.maintenance_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {"enabled": False}
        except (json.JSONDecodeError, OSError):
            return {"enabled": True, "reason": "maintenance_state_unreadable"}
        if not isinstance(payload, dict) or payload.get("enabled") is not True:
            return {"enabled": True, "reason": "maintenance_state_malformed"}
        return payload
