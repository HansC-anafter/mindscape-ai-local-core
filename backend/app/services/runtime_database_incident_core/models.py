"""Typed contracts for the runtime database incident mutation gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Optional


class IncidentState(str, Enum):
    """Allowed durable incident states."""

    OPEN_UNATTRIBUTED = "open_unattributed"
    CONTAINED_PENDING_SOAK = "contained_pending_soak"
    CLOSED = "closed"


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
        missing = [name for name, value in values.items() if not str(value).strip()]
        if not self.test_evidence_paths or any(
            not str(path).strip() for path in self.test_evidence_paths
        ):
            missing.append("test_evidence_paths")
        if missing:
            raise ValueError(
                "Incident close receipt is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )

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
            close_receipt=payload.get("close_receipt"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
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
