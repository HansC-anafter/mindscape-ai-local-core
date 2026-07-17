"""Typed contracts for the runtime database incident mutation gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping, Optional


class IncidentState(str, Enum):
    """Allowed durable incident states."""

    OPEN_UNATTRIBUTED = "open_unattributed"
    CONTAINED_PENDING_SOAK = "contained_pending_soak"
    CLOSED = "closed"


def _required_text(values: Mapping[str, str]) -> list[str]:
    return [name for name, value in values.items() if not str(value).strip()]


def _parse_timestamp(value: str, *, field_name: str) -> datetime:
    normalized = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(f"{field_name}_must_be_iso8601") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"{field_name}_must_include_timezone")
    return parsed


@dataclass(frozen=True)
class IncidentContainmentReceipt:
    """Exact, expiring operations allowed while an incident remains open."""

    permit_id: str
    trigger_classification: str
    fix_commit: str
    allowed_operation_keys: tuple[str, ...]
    test_evidence_paths: tuple[str, ...]
    restore_id: str
    expires_at: str
    owner: str

    def validate(self) -> None:
        missing = _required_text(
            {
                "permit_id": self.permit_id,
                "trigger_classification": self.trigger_classification,
                "fix_commit": self.fix_commit,
                "restore_id": self.restore_id,
                "expires_at": self.expires_at,
                "owner": self.owner,
            }
        )
        if not self.allowed_operation_keys or any(
            not str(value).strip() for value in self.allowed_operation_keys
        ):
            missing.append("allowed_operation_keys")
        if not self.test_evidence_paths or any(
            not str(path).strip() for path in self.test_evidence_paths
        ):
            missing.append("test_evidence_paths")
        if missing:
            raise ValueError(
                "Incident containment receipt is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )
        if len(self.allowed_operation_keys) > 64:
            raise ValueError("containment_operation_key_limit_exceeded")
        if len(set(self.allowed_operation_keys)) != len(self.allowed_operation_keys):
            raise ValueError("containment_operation_keys_must_be_unique")
        for key in self.allowed_operation_keys:
            normalized = str(key).strip()
            if len(normalized) > 256:
                raise ValueError("containment_operation_key_too_long")
            if "*" in normalized or any(char.isspace() for char in normalized):
                raise ValueError("containment_operation_keys_must_be_exact")
        _parse_timestamp(self.expires_at, field_name="containment_expires_at")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_operation_keys"] = list(self.allowed_operation_keys)
        payload["test_evidence_paths"] = list(self.test_evidence_paths)
        return payload


@dataclass(frozen=True)
class IncidentCloseReceipt:
    """Evidence required before an incident may be closed."""

    deep_trigger_classification: str
    fix_commit: str
    test_evidence_paths: tuple[str, ...]
    soak_window: str
    restore_id: str
    owner: str

    def validate(self) -> None:
        values = {
            "deep_trigger_classification": self.deep_trigger_classification,
            "fix_commit": self.fix_commit,
            "soak_window": self.soak_window,
            "restore_id": self.restore_id,
            "owner": self.owner,
        }
        missing = _required_text(values)
        if not self.test_evidence_paths or any(
            not str(path).strip() for path in self.test_evidence_paths
        ):
            missing.append("test_evidence_paths")
        if missing:
            raise ValueError(
                "Incident close receipt is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )
        classification = self.deep_trigger_classification.strip().lower()
        forbidden = ("unknown", "unattributed", "undetermined", "unresolved")
        if any(marker in classification for marker in forbidden):
            raise ValueError("incident_close_requires_attributed_deep_trigger")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["test_evidence_paths"] = list(self.test_evidence_paths)
        return payload


@dataclass(frozen=True)
class IncidentReceipt:
    """Current durable state of one runtime database incident."""

    incident_id: str
    state: IncidentState
    failure_code: str
    postmaster_start_time: str
    first_failure_at: str
    updated_at: str
    evidence_count: int
    containment_receipt: Optional[Mapping[str, Any]] = None
    close_receipt: Optional[Mapping[str, Any]] = None

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "IncidentReceipt":
        return cls(
            incident_id=str(payload["incident_id"]),
            state=IncidentState(str(payload["state"])),
            failure_code=str(payload["failure_code"]),
            postmaster_start_time=str(payload["postmaster_start_time"]),
            first_failure_at=str(payload["first_failure_at"]),
            updated_at=str(payload["updated_at"]),
            evidence_count=int(payload.get("evidence_count", 0)),
            containment_receipt=payload.get("containment_receipt"),
            close_receipt=payload.get("close_receipt"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        if self.containment_receipt is None:
            payload.pop("containment_receipt", None)
        if self.close_receipt is None:
            payload.pop("close_receipt", None)
        return payload


@dataclass(frozen=True)
class MutationDecision:
    """Stable mutation admission response used by all callers."""

    allowed: bool
    operation: str
    reason: str
    incident_id: Optional[str] = None
    retry_after_seconds: int = 30
    details: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
