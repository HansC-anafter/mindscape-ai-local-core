"""Same-journal terminal transitions for runtime database incidents."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from typing import Any, Mapping

from .closure_policy import (
    IncidentClosurePolicyError,
    validate_attributable_close,
    validate_residual_close,
)
from .closure_receipts import (
    IncidentAttributionExhaustionReceipt,
    IncidentResidualCloseReceipt,
)
from .models import IncidentCloseReceipt, IncidentReceipt, IncidentState


class IncidentTransitionError(RuntimeError):
    """Raised when a caller attempts an invalid incident transition."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class IncidentClosureJournalMixin:
    """Add bounded exhaustion and strict terminal closure to the journal."""

    def close(
        self,
        incident_id: str,
        close_receipt: IncidentCloseReceipt,
    ) -> IncidentReceipt:
        close_receipt.validate()
        with self._lock():
            current = self._require_current_unlocked(incident_id)
            if current.state is IncidentState.CLOSED:
                expected = close_receipt.to_dict()
                expected["closure_mode"] = "attributable"
                if current.close_receipt == expected:
                    return current
                raise IncidentTransitionError(
                    f"Incident {incident_id} is already closed with another receipt"
                )
            events = self._read_events_unlocked(incident_id)
            try:
                close_payload = validate_attributable_close(
                    current,
                    close_receipt,
                    events,
                )
            except IncidentClosurePolicyError as exc:
                raise IncidentTransitionError(str(exc)) from exc
            return self._finalize_close_unlocked(
                current,
                close_payload=close_payload,
            )

    def record_attribution_exhaustion(
        self,
        incident_id: str,
        exhaustion_receipt: IncidentAttributionExhaustionReceipt,
    ) -> IncidentReceipt:
        exhaustion_receipt.validate()
        if exhaustion_receipt.incident_id != incident_id:
            raise ValueError("attribution_exhaustion_incident_id_mismatch")
        payload = exhaustion_receipt.to_dict()
        payload_sha256 = exhaustion_receipt.sha256()
        with self._lock():
            current = self._require_current_unlocked(incident_id)
            if current.state is not IncidentState.OPEN_UNATTRIBUTED:
                raise IncidentTransitionError(
                    f"Incident {incident_id} must remain open for attribution exhaustion"
                )
            events = self._read_events_unlocked(incident_id)
            exhaustion_events = [
                event
                for event in events
                if event.get("event") == "attribution_exhaustion_recorded"
            ]
            if exhaustion_events:
                existing = exhaustion_events[0]
                if (
                    len(exhaustion_events) == 1
                    and existing.get("attribution_exhaustion_sha256")
                    == payload_sha256
                    and existing.get("attribution_exhaustion_receipt") == payload
                ):
                    return current
                raise IncidentTransitionError(
                    "incident_attribution_exhaustion_already_recorded"
                )
            event_time = _utc_now()
            updated = replace(
                current,
                updated_at=event_time,
                evidence_count=current.evidence_count + 1,
            )
            self._append_event_unlocked(
                incident_id=incident_id,
                event={
                    "event": "attribution_exhaustion_recorded",
                    "at": event_time,
                    "attribution_exhaustion_sha256": payload_sha256,
                    "attribution_exhaustion_receipt": payload,
                },
            )
            self._write_current_unlocked(updated)
            return updated

    def close_residual(
        self,
        incident_id: str,
        close_receipt: IncidentResidualCloseReceipt,
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
            events = self._read_events_unlocked(incident_id)
            try:
                close_payload = validate_residual_close(
                    current,
                    close_receipt,
                    events,
                )
            except IncidentClosurePolicyError as exc:
                raise IncidentTransitionError(str(exc)) from exc
            return self._finalize_close_unlocked(
                current,
                close_payload=close_payload,
            )

    def _finalize_close_unlocked(
        self,
        current: IncidentReceipt,
        *,
        close_payload: Mapping[str, Any],
    ) -> IncidentReceipt:
        event_time = _utc_now()
        updated = replace(
            current,
            state=IncidentState.CLOSED,
            updated_at=event_time,
            diagnostic_permit=None,
            containment_receipt=None,
            close_receipt=close_payload,
        )
        self._append_event_unlocked(
            incident_id=current.incident_id,
            event={
                "event": "incident_closed",
                "at": event_time,
                "closure_mode": close_payload.get("closure_mode"),
                "close_receipt": dict(close_payload),
            },
        )
        self._write_current_unlocked(updated)
        return updated
