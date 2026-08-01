"""Same-journal terminal transitions for runtime database incidents."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
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

    def reopen_for_attribution(
        self,
        incident_id: str,
        *,
        owner: str,
        authorization: str,
        authorization_path: str,
        authorization_sha256: str,
        reason: str,
    ) -> IncidentReceipt:
        """Re-open a prematurely contained incident through an owner receipt.

        Containment must follow attribution exhaustion for the residual-close
        contract. This narrow repair path preserves the original containment
        event, clears only the current containment projection, and returns the
        incident to ``open_unattributed`` so the canonical bounded-search
        facade can append the required exhaustion event. It cannot operate on
        a closed incident or one that already has an exhaustion event.
        """

        if owner != "runtime-db-incident-owner":
            raise ValueError("attribution_reopen_owner_invalid")
        if reason != "containment_preceded_attribution_exhaustion":
            raise ValueError("attribution_reopen_reason_invalid")
        if not authorization.strip() or not authorization_path.strip():
            raise ValueError("attribution_reopen_authorization_missing")
        if len(authorization_sha256) != 64 or any(
            character not in "0123456789abcdef"
            for character in authorization_sha256
        ):
            raise ValueError("attribution_reopen_authorization_sha256_invalid")
        try:
            actual_sha256 = hashlib.sha256(
                Path(authorization_path).read_bytes()
            ).hexdigest()
        except OSError as exc:
            raise ValueError("attribution_reopen_authorization_unavailable") from exc
        if actual_sha256 != authorization_sha256:
            raise ValueError("attribution_reopen_authorization_sha256_mismatch")

        with self._lock():
            current = self._require_current_unlocked(incident_id)
            if current.state is IncidentState.OPEN_UNATTRIBUTED:
                if current.containment_receipt is None:
                    return current
                raise IncidentTransitionError(
                    "Incident already open with unexpected containment projection"
                )
            if current.state is IncidentState.CLOSED:
                raise IncidentTransitionError(
                    "Closed incidents cannot be reopened for attribution"
                )
            events = self._read_events_unlocked(incident_id)
            if any(
                event.get("event") == "attribution_exhaustion_recorded"
                for event in events
            ):
                raise IncidentTransitionError(
                    "Attribution exhaustion already recorded"
                )
            if current.containment_receipt is None:
                raise IncidentTransitionError(
                    "Contained incident has no current containment receipt"
                )
            event_time = _utc_now()
            updated = replace(
                current,
                state=IncidentState.OPEN_UNATTRIBUTED,
                updated_at=event_time,
                evidence_count=current.evidence_count + 1,
                containment_receipt=None,
            )
            self._append_event_unlocked(
                incident_id=incident_id,
                event={
                    "event": "containment_reopened_for_attribution",
                    "at": event_time,
                    "reason": reason,
                    "owner": owner,
                    "authorization": authorization,
                    "authorization_path": authorization_path,
                    "authorization_sha256": authorization_sha256,
                    "revoked_containment_receipt": current.containment_receipt,
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
