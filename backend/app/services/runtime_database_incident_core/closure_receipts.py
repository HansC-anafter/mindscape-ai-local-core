"""Typed receipts for bounded residual-attribution incident closure."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any

from .models import _parse_timestamp, _required_text, _validate_sha256


ATTRIBUTION_EXHAUSTION_CLASSIFICATION = (
    "historical_event_irretrievable_after_bounded_search"
)
RESIDUAL_CLOSURE_MODE = "residual_attribution_gap"
RESIDUAL_RISK_STATEMENT = "event_time_sender_identity_unrecoverable"
RESIDUAL_OWNER = "runtime-db-incident-owner"
REQUIRED_SEARCHED_SOURCES = frozenset(
    {
        "codex_tool_calls",
        "docker_event_history",
        "incident_journal",
        "postgres_container_logs",
        "postgres_file_logs",
        "runtime_core_dumps",
        "signal_observer_events",
        "zsh_extended_history",
    }
)


def canonical_receipt_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class IncidentAttributionExhaustionReceipt:
    """One owner-authorized, bounded negative-evidence attribution sweep."""

    incident_id: str
    classification: str
    search_started_at: str
    search_ended_at: str
    searched_sources: tuple[str, ...]
    evidence_bundle_path: str
    evidence_bundle_sha256: str
    residual_risk_statement: str
    owner: str
    owner_authorization: str
    owner_authorization_path: str
    owner_authorization_sha256: str
    search_complete: bool

    def validate(self) -> None:
        missing = _required_text(
            {
                "incident_id": self.incident_id,
                "classification": self.classification,
                "search_started_at": self.search_started_at,
                "search_ended_at": self.search_ended_at,
                "evidence_bundle_path": self.evidence_bundle_path,
                "evidence_bundle_sha256": self.evidence_bundle_sha256,
                "residual_risk_statement": self.residual_risk_statement,
                "owner": self.owner,
                "owner_authorization": self.owner_authorization,
                "owner_authorization_path": self.owner_authorization_path,
                "owner_authorization_sha256": self.owner_authorization_sha256,
            }
        )
        if missing:
            raise ValueError(
                "Attribution exhaustion receipt is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )
        if self.classification != ATTRIBUTION_EXHAUSTION_CLASSIFICATION:
            raise ValueError("attribution_exhaustion_classification_invalid")
        if self.residual_risk_statement != RESIDUAL_RISK_STATEMENT:
            raise ValueError("attribution_exhaustion_residual_risk_invalid")
        if self.owner != RESIDUAL_OWNER:
            raise ValueError("attribution_exhaustion_owner_invalid")
        if self.search_complete is not True:
            raise ValueError("attribution_exhaustion_search_incomplete")
        if len(self.searched_sources) != len(set(self.searched_sources)):
            raise ValueError("attribution_exhaustion_sources_must_be_unique")
        if set(self.searched_sources) != REQUIRED_SEARCHED_SOURCES:
            raise ValueError("attribution_exhaustion_sources_incomplete")
        started_at = _parse_timestamp(
            self.search_started_at,
            field_name="attribution_search_started_at",
        )
        ended_at = _parse_timestamp(
            self.search_ended_at,
            field_name="attribution_search_ended_at",
        )
        if ended_at <= started_at:
            raise ValueError("attribution_exhaustion_search_window_invalid")
        if ended_at - started_at > timedelta(minutes=30):
            raise ValueError("attribution_exhaustion_search_exceeds_30_minutes")
        if ended_at > datetime.now(timezone.utc):
            raise ValueError("attribution_exhaustion_search_not_complete")
        _validate_sha256(
            self.evidence_bundle_sha256,
            field_name="attribution_evidence_bundle_sha256",
        )
        _validate_sha256(
            self.owner_authorization_sha256,
            field_name="attribution_owner_authorization_sha256",
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["searched_sources"] = list(self.searched_sources)
        return payload

    def sha256(self) -> str:
        return canonical_receipt_sha256(self.to_dict())


@dataclass(frozen=True)
class IncidentResidualCloseReceipt:
    """Full P0 closure bundle for an irretrievable historical trigger."""

    closure_mode: str
    attribution_exhaustion_sha256: str
    residual_risk_statement: str
    fix_commit: str
    containment_evidence_path: str
    containment_evidence_sha256: str
    test_evidence_paths: tuple[str, ...]
    test_evidence_sha256: str
    reproduction_evidence_path: str
    reproduction_evidence_sha256: str
    soak_window: str
    restore_id: str
    restore_evidence_path: str
    restore_evidence_sha256: str
    resource_budget_evidence_path: str
    resource_budget_evidence_sha256: str
    owner: str
    owner_receipt_path: str
    owner_receipt_sha256: str

    def validate(self) -> None:
        values = {
            "closure_mode": self.closure_mode,
            "attribution_exhaustion_sha256": self.attribution_exhaustion_sha256,
            "residual_risk_statement": self.residual_risk_statement,
            "fix_commit": self.fix_commit,
            "containment_evidence_path": self.containment_evidence_path,
            "containment_evidence_sha256": self.containment_evidence_sha256,
            "test_evidence_sha256": self.test_evidence_sha256,
            "reproduction_evidence_path": self.reproduction_evidence_path,
            "reproduction_evidence_sha256": self.reproduction_evidence_sha256,
            "soak_window": self.soak_window,
            "restore_id": self.restore_id,
            "restore_evidence_path": self.restore_evidence_path,
            "restore_evidence_sha256": self.restore_evidence_sha256,
            "resource_budget_evidence_path": self.resource_budget_evidence_path,
            "resource_budget_evidence_sha256": self.resource_budget_evidence_sha256,
            "owner": self.owner,
            "owner_receipt_path": self.owner_receipt_path,
            "owner_receipt_sha256": self.owner_receipt_sha256,
        }
        missing = _required_text(values)
        if not self.test_evidence_paths or any(
            not str(path).strip() for path in self.test_evidence_paths
        ):
            missing.append("test_evidence_paths")
        if missing:
            raise ValueError(
                "Residual close receipt is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )
        if self.closure_mode != RESIDUAL_CLOSURE_MODE:
            raise ValueError("residual_close_mode_invalid")
        if self.residual_risk_statement != RESIDUAL_RISK_STATEMENT:
            raise ValueError("residual_close_risk_statement_invalid")
        if self.owner != RESIDUAL_OWNER:
            raise ValueError("residual_close_owner_invalid")
        if not re.fullmatch(r"[0-9a-f]{40}", self.fix_commit):
            raise ValueError("residual_close_fix_commit_must_be_exact")
        for field_name, value in {
            "attribution_exhaustion_sha256": self.attribution_exhaustion_sha256,
            "containment_evidence_sha256": self.containment_evidence_sha256,
            "test_evidence_sha256": self.test_evidence_sha256,
            "reproduction_evidence_sha256": self.reproduction_evidence_sha256,
            "restore_evidence_sha256": self.restore_evidence_sha256,
            "resource_budget_evidence_sha256": self.resource_budget_evidence_sha256,
            "owner_receipt_sha256": self.owner_receipt_sha256,
        }.items():
            _validate_sha256(value, field_name=field_name)
        restore_id = self.restore_id.strip().lower()
        if any(
            marker in restore_id
            for marker in ("not_required", "not-required", "unknown", "unavailable")
        ) or restore_id in {"none", "n/a", "na"}:
            raise ValueError("residual_close_requires_restore_evidence")
        boundaries = self.soak_window.split("/")
        if len(boundaries) != 2:
            raise ValueError("residual_close_soak_window_invalid")
        soak_started_at = _parse_timestamp(
            boundaries[0],
            field_name="residual_close_soak_started_at",
        )
        soak_ended_at = _parse_timestamp(
            boundaries[1],
            field_name="residual_close_soak_ended_at",
        )
        if soak_ended_at <= soak_started_at:
            raise ValueError("residual_close_soak_window_invalid")
        if soak_ended_at > datetime.now(timezone.utc):
            raise ValueError("residual_close_soak_window_not_complete")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["test_evidence_paths"] = list(self.test_evidence_paths)
        return payload
