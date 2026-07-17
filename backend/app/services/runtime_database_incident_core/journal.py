"""Append-only filesystem journal for runtime database incidents."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import tempfile
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Mapping, Optional

from .models import (
    IncidentCloseReceipt,
    IncidentContainmentReceipt,
    IncidentDiagnosticPermit,
    IncidentReceipt,
    IncidentState,
    _parse_timestamp,
)


DEFAULT_INCIDENT_DIRECTORY = Path("/app/data/runtime-database-incidents")
CURRENT_RECEIPT_NAME = "current.json"
LOCK_NAME = ".journal.lock"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def incident_directory() -> Path:
    configured = os.getenv("RUNTIME_DATABASE_INCIDENT_DIR", "").strip()
    return Path(configured) if configured else DEFAULT_INCIDENT_DIRECTORY


class IncidentJournalUnavailable(RuntimeError):
    """Raised when the single durable journal cannot be read or written."""


class IncidentTransitionError(RuntimeError):
    """Raised when a caller attempts an invalid incident transition."""


class RuntimeDatabaseIncidentJournal:
    """Serialize incident state and evidence through one cross-process lock."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root is not None else incident_directory()
        self.current_path = self.root / CURRENT_RECEIPT_NAME
        self.lock_path = self.root / LOCK_NAME

    def _ensure_root(self) -> None:
        try:
            self.root.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise IncidentJournalUnavailable(
                f"Runtime database incident journal is unavailable: {self.root}"
            ) from exc

    @contextmanager
    def _lock(self) -> Iterator[None]:
        self._ensure_root()
        try:
            with self.lock_path.open("a+", encoding="utf-8") as lock_file:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
        except OSError as exc:
            raise IncidentJournalUnavailable(
                f"Runtime database incident journal lock is unavailable: {self.lock_path}"
            ) from exc

    def _read_current_unlocked(self) -> Optional[IncidentReceipt]:
        if not self.current_path.exists():
            return None
        try:
            payload = json.loads(self.current_path.read_text(encoding="utf-8"))
            return IncidentReceipt.from_dict(payload)
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise IncidentJournalUnavailable(
                f"Runtime database incident receipt is unreadable: {self.current_path}"
            ) from exc

    def current(self) -> Optional[IncidentReceipt]:
        with self._lock():
            return self._read_current_unlocked()

    def _incident_path(self, incident_id: str) -> Path:
        digest = hashlib.sha256(incident_id.encode("utf-8")).hexdigest()[:20]
        return self.root / "incidents" / digest

    def _append_event_unlocked(
        self,
        *,
        incident_id: str,
        event: Mapping[str, Any],
    ) -> None:
        incident_path = self._incident_path(incident_id)
        incident_path.mkdir(parents=True, exist_ok=True)
        event_path = incident_path / "events.jsonl"
        serialized = json.dumps(event, sort_keys=True, separators=(",", ":"))
        try:
            with event_path.open("a", encoding="utf-8") as event_file:
                event_file.write(serialized + "\n")
                event_file.flush()
                os.fsync(event_file.fileno())
        except OSError as exc:
            raise IncidentJournalUnavailable(
                f"Runtime database incident event append failed: {event_path}"
            ) from exc

    def _write_current_unlocked(self, receipt: IncidentReceipt) -> None:
        self._ensure_root()
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.root,
                prefix=".current-",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                json.dump(
                    receipt.to_dict(),
                    temporary,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                temporary.write("\n")
                temporary.flush()
                os.fsync(temporary.fileno())
                temporary_path = Path(temporary.name)
            os.replace(temporary_path, self.current_path)
            directory_fd = os.open(self.root, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except OSError as exc:
            raise IncidentJournalUnavailable(
                f"Runtime database incident receipt write failed: {self.current_path}"
            ) from exc

    def open_incident(
        self,
        *,
        failure_code: str,
        postmaster_start_time: str = "unknown",
        first_failure_at: Optional[str] = None,
        evidence: Optional[Mapping[str, Any]] = None,
    ) -> IncidentReceipt:
        failure_at = first_failure_at or utc_now()
        with self._lock():
            current = self._read_current_unlocked()
            event_time = utc_now()
            if current is not None and current.state is not IncidentState.CLOSED:
                revoked_diagnostic = current.diagnostic_permit
                revoked_containment = current.containment_receipt
                updated = replace(
                    current,
                    state=IncidentState.OPEN_UNATTRIBUTED,
                    updated_at=event_time,
                    evidence_count=current.evidence_count + 1,
                    diagnostic_permit=None,
                    containment_receipt=None,
                )
                if revoked_containment is not None:
                    self._append_event_unlocked(
                        incident_id=current.incident_id,
                        event={
                            "event": "containment_revoked_by_failure",
                            "at": event_time,
                            "permit_id": revoked_containment.get("permit_id"),
                            "failure_code": failure_code,
                        },
                    )
                elif revoked_diagnostic is not None:
                    self._append_event_unlocked(
                        incident_id=current.incident_id,
                        event={
                            "event": "diagnostic_permit_revoked_by_failure",
                            "at": event_time,
                            "permit_id": revoked_diagnostic.get("permit_id"),
                            "failure_code": failure_code,
                        },
                    )
                self._append_event_unlocked(
                    incident_id=current.incident_id,
                    event={
                        "event": "failure_observed",
                        "at": event_time,
                        "failure_code": failure_code,
                        "evidence": dict(evidence or {}),
                    },
                )
                self._write_current_unlocked(updated)
                return updated

            incident_id = f"postgres:{postmaster_start_time or 'unknown'}:{failure_at}"
            receipt = IncidentReceipt(
                incident_id=incident_id,
                state=IncidentState.OPEN_UNATTRIBUTED,
                failure_code=failure_code,
                postmaster_start_time=postmaster_start_time or "unknown",
                first_failure_at=failure_at,
                updated_at=event_time,
                evidence_count=1,
            )
            self._append_event_unlocked(
                incident_id=incident_id,
                event={
                    "event": "incident_opened",
                    "at": event_time,
                    "failure_code": failure_code,
                    "evidence": dict(evidence or {}),
                },
            )
            self._write_current_unlocked(receipt)
            return receipt

    def record_diagnostic_permit(
        self,
        incident_id: str,
        diagnostic_permit: IncidentDiagnosticPermit,
    ) -> IncidentReceipt:
        diagnostic_permit.validate()
        with self._lock():
            current = self._require_current_unlocked(incident_id)
            if current.state is not IncidentState.OPEN_UNATTRIBUTED:
                raise IncidentTransitionError(
                    f"Incident {incident_id} must remain open for diagnostic permit"
                )
            payload = diagnostic_permit.to_dict()
            if current.diagnostic_permit == payload:
                return current
            if current.diagnostic_permit is not None:
                existing_expiry = _parse_timestamp(
                    str(current.diagnostic_permit.get("expires_at") or ""),
                    field_name="diagnostic_expires_at",
                )
                if existing_expiry > datetime.now(timezone.utc):
                    raise IncidentTransitionError(
                        f"Incident {incident_id} already has another diagnostic permit"
                    )
            event_time = utc_now()
            if current.diagnostic_permit is not None:
                self._append_event_unlocked(
                    incident_id=incident_id,
                    event={
                        "event": "diagnostic_permit_expired",
                        "at": event_time,
                        "permit_id": current.diagnostic_permit.get("permit_id"),
                    },
                )
            updated = replace(
                current,
                updated_at=event_time,
                diagnostic_permit=payload,
            )
            self._append_event_unlocked(
                incident_id=incident_id,
                event={
                    "event": "diagnostic_permit_recorded",
                    "at": event_time,
                    "diagnostic_permit": payload,
                },
            )
            self._write_current_unlocked(updated)
            return updated

    def mark_contained(
        self,
        incident_id: str,
        containment_receipt: IncidentContainmentReceipt,
    ) -> IncidentReceipt:
        containment_receipt.validate()
        if _parse_timestamp(
            containment_receipt.expires_at,
            field_name="containment_expires_at",
        ) <= datetime.now(timezone.utc):
            raise ValueError("containment_receipt_expired")
        with self._lock():
            current = self._require_current_unlocked(incident_id)
            if current.state is IncidentState.CONTAINED_PENDING_SOAK:
                if current.containment_receipt == containment_receipt.to_dict():
                    return current
                raise IncidentTransitionError(
                    f"Incident {incident_id} is already contained with another receipt"
                )
            if current.state is not IncidentState.OPEN_UNATTRIBUTED:
                raise IncidentTransitionError(
                    f"Incident {incident_id} cannot transition from {current.state.value} to contained"
                )
            event_time = utc_now()
            updated = replace(
                current,
                state=IncidentState.CONTAINED_PENDING_SOAK,
                updated_at=event_time,
                diagnostic_permit=None,
                containment_receipt=containment_receipt.to_dict(),
            )
            self._append_event_unlocked(
                incident_id=incident_id,
                event={
                    "event": "incident_contained",
                    "at": event_time,
                    "containment_receipt": containment_receipt.to_dict(),
                },
            )
            self._write_current_unlocked(updated)
            return updated

    def close(
        self,
        incident_id: str,
        close_receipt: IncidentCloseReceipt,
    ) -> IncidentReceipt:
        close_receipt.validate()
        with self._lock():
            current = self._require_current_unlocked(incident_id)
            if current.state is IncidentState.CLOSED:
                if current.close_receipt == close_receipt.to_dict():
                    return current
                raise IncidentTransitionError(
                    f"Incident {incident_id} is already closed with another receipt"
                )
            if current.state is not IncidentState.CONTAINED_PENDING_SOAK:
                raise IncidentTransitionError(
                    f"Incident {incident_id} must be contained before close"
                )
            event_time = utc_now()
            close_payload = close_receipt.to_dict()
            updated = replace(
                current,
                state=IncidentState.CLOSED,
                updated_at=event_time,
                close_receipt=close_payload,
            )
            self._append_event_unlocked(
                incident_id=incident_id,
                event={
                    "event": "incident_closed",
                    "at": event_time,
                    "close_receipt": close_payload,
                },
            )
            self._write_current_unlocked(updated)
            return updated

    def _require_current_unlocked(self, incident_id: str) -> IncidentReceipt:
        current = self._read_current_unlocked()
        if current is None or current.incident_id != incident_id:
            raise IncidentTransitionError(f"Incident {incident_id} is not current")
        return current
