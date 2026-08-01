"""Machine-verifiable terminal policies for runtime database incidents."""

from __future__ import annotations

from typing import Any, Mapping

from .closure_receipts import (
    ATTRIBUTION_EXHAUSTION_CLASSIFICATION,
    RESIDUAL_RISK_STATEMENT,
    IncidentResidualCloseReceipt,
)
from .models import IncidentCloseReceipt, IncidentReceipt, IncidentState, _parse_timestamp


class IncidentClosurePolicyError(ValueError):
    """Raised when same-journal terminal evidence is incomplete or inconsistent."""


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _require_common_close_evidence(
    current: IncidentReceipt,
    close_receipt: IncidentCloseReceipt | IncidentResidualCloseReceipt,
    events: list[Mapping[str, Any]],
) -> tuple[dict[str, Any], object]:
    if current.state is not IncidentState.CONTAINED_PENDING_SOAK:
        raise IncidentClosurePolicyError(
            f"Incident {current.incident_id} must be contained before close"
        )
    containment = dict(current.containment_receipt or {})
    if close_receipt.fix_commit != containment.get("fix_commit"):
        raise IncidentClosurePolicyError(
            "incident_close_fix_commit_must_match_containment"
        )
    if close_receipt.restore_id != containment.get("restore_id"):
        raise IncidentClosurePolicyError(
            "incident_close_restore_id_must_match_containment"
        )
    if close_receipt.owner != containment.get("owner"):
        raise IncidentClosurePolicyError(
            "incident_close_owner_must_match_containment"
        )
    containment_tests = set(containment.get("test_evidence_paths") or ())
    if not containment_tests.issubset(set(close_receipt.test_evidence_paths)):
        raise IncidentClosurePolicyError(
            "incident_close_tests_must_include_containment_evidence"
        )
    latest_reopen_at = None
    reopen_events = [
        event
        for event in events
        if event.get("event") == "containment_reopened_for_attribution"
    ]
    if reopen_events:
        latest_reopen_at = max(
            _parse_timestamp(
                str(event.get("at") or ""),
                field_name="containment_reopened_at",
            )
            for event in reopen_events
        )
    contained_events = []
    for event in events:
        if (
            event.get("event") != "incident_contained"
            or event.get("containment_receipt") != containment
        ):
            continue
        if latest_reopen_at is not None:
            contained_at = _parse_timestamp(
                str(event.get("at") or ""),
                field_name="incident_contained_at",
            )
            if contained_at <= latest_reopen_at:
                continue
        contained_events.append(event)
    if len(contained_events) != 1:
        raise IncidentClosurePolicyError(
            "incident_close_requires_exact_current_containment_event"
        )
    contained_at = _parse_timestamp(
        str(contained_events[0].get("at") or ""),
        field_name="incident_contained_at",
    )
    soak_started_at = _parse_timestamp(
        close_receipt.soak_window.split("/")[0],
        field_name="incident_close_soak_started_at",
    )
    if soak_started_at < contained_at:
        raise IncidentClosurePolicyError(
            "incident_close_soak_must_follow_containment"
        )
    return containment, contained_at


def validate_attributable_close(
    current: IncidentReceipt,
    close_receipt: IncidentCloseReceipt,
    events: list[Mapping[str, Any]],
) -> dict[str, Any]:
    _require_common_close_evidence(current, close_receipt, events)
    matching_trigger_events = [
        event
        for event in events
        if event.get("event") == "diagnostic_observation_recorded"
        and event.get("observation_code") == "postgres_sigquit_signal_observed"
        and isinstance(event.get("evidence"), Mapping)
        and event["evidence"].get("event_context") == "live_runtime"
        and event["evidence"].get("signal_event_sha256")
        == close_receipt.deep_trigger_event_sha256
        and str(event["evidence"].get("sender_comm") or "").strip()
        and _positive_int(event["evidence"].get("sender_host_pid")) is not None
        and _positive_int(event["evidence"].get("target_host_pid")) is not None
        and _positive_int(event["evidence"].get("target_postgres_pid")) is not None
        and str(event["evidence"].get("application_name") or "").strip()
        and event["evidence"].get("client_process_pid_available") == "true"
        and _positive_int(event["evidence"].get("client_process_pid")) is not None
        and str(event["evidence"].get("signal_event_path") or "").strip()
    ]
    if len(matching_trigger_events) != 1:
        raise IncidentClosurePolicyError(
            "incident_close_requires_exact_live_deep_trigger_event"
        )
    payload = close_receipt.to_dict()
    payload["closure_mode"] = "attributable"
    return payload


def validate_residual_close(
    current: IncidentReceipt,
    close_receipt: IncidentResidualCloseReceipt,
    events: list[Mapping[str, Any]],
) -> dict[str, Any]:
    _, contained_at = _require_common_close_evidence(
        current,
        close_receipt,
        events,
    )
    exhaustion_events = [
        event
        for event in events
        if event.get("event") == "attribution_exhaustion_recorded"
    ]
    if len(exhaustion_events) != 1:
        raise IncidentClosurePolicyError(
            "residual_close_requires_exact_attribution_exhaustion_event"
        )
    exhaustion_event = exhaustion_events[0]
    exhaustion = exhaustion_event.get("attribution_exhaustion_receipt")
    if (
        exhaustion_event.get("attribution_exhaustion_sha256")
        != close_receipt.attribution_exhaustion_sha256
        or not isinstance(exhaustion, Mapping)
        or exhaustion.get("incident_id") != current.incident_id
        or exhaustion.get("classification")
        != ATTRIBUTION_EXHAUSTION_CLASSIFICATION
        or exhaustion.get("residual_risk_statement")
        != RESIDUAL_RISK_STATEMENT
        or exhaustion.get("search_complete") is not True
    ):
        raise IncidentClosurePolicyError(
            "residual_close_attribution_exhaustion_mismatch"
        )
    exhaustion_at = _parse_timestamp(
        str(exhaustion_event.get("at") or ""),
        field_name="attribution_exhaustion_recorded_at",
    )
    if exhaustion_at > contained_at:
        raise IncidentClosurePolicyError(
            "residual_close_exhaustion_must_precede_containment"
        )
    return close_receipt.to_dict()
