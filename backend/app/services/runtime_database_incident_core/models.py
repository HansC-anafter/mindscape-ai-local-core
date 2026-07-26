"""Typed contracts for the runtime database incident mutation gate."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import re
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


_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_DIAGNOSTIC_OPERATION_PATTERNS = (
    re.compile(r"^postgres_signal_observer_start@sha256:[0-9a-f]{64}$"),
    re.compile(r"^postgres_identity_logging_reload@sha256:[0-9a-f]{64}$"),
)


@dataclass(frozen=True)
class IncidentDiagnosticPermit:
    """Exact short-lived observability operations allowed while incident stays open."""

    permit_id: str
    source_commit: str
    allowed_operation_keys: tuple[str, ...]
    test_evidence_paths: tuple[str, ...]
    capture_evidence_id: str
    budget_sha256: str
    expires_at: str
    owner: str

    def validate(self) -> None:
        missing = _required_text(
            {
                "permit_id": self.permit_id,
                "source_commit": self.source_commit,
                "capture_evidence_id": self.capture_evidence_id,
                "budget_sha256": self.budget_sha256,
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
                "Incident diagnostic permit is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )
        if not _SHA256_PATTERN.fullmatch(self.budget_sha256):
            raise ValueError("diagnostic_budget_sha256_invalid")
        if not re.fullmatch(r"[0-9a-f]{8,64}", self.source_commit):
            raise ValueError("diagnostic_source_commit_invalid")
        if len(self.allowed_operation_keys) > 2:
            raise ValueError("diagnostic_operation_key_limit_exceeded")
        if len(set(self.allowed_operation_keys)) != len(self.allowed_operation_keys):
            raise ValueError("diagnostic_operation_keys_must_be_unique")
        for key in self.allowed_operation_keys:
            if not any(
                pattern.fullmatch(key) for pattern in _DIAGNOSTIC_OPERATION_PATTERNS
            ):
                raise ValueError("diagnostic_operation_key_not_allowed")
        expires_at = _parse_timestamp(
            self.expires_at,
            field_name="diagnostic_expires_at",
        )
        now = datetime.now(timezone.utc)
        if expires_at <= now:
            raise ValueError("diagnostic_permit_expired")
        if expires_at > now + timedelta(minutes=30):
            raise ValueError("diagnostic_permit_duration_exceeds_30_minutes")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_operation_keys"] = list(self.allowed_operation_keys)
        payload["test_evidence_paths"] = list(self.test_evidence_paths)
        return payload


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
        if not re.fullmatch(r"[0-9a-f]{40}", self.fix_commit):
            raise ValueError("containment_fix_commit_must_be_exact")
        _parse_timestamp(self.expires_at, field_name="containment_expires_at")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_operation_keys"] = list(self.allowed_operation_keys)
        payload["test_evidence_paths"] = list(self.test_evidence_paths)
        return payload


def _validate_sha256(value: str, *, field_name: str) -> None:
    normalized = str(value).strip().lower()
    if len(normalized) != 64 or any(
        character not in "0123456789abcdef" for character in normalized
    ):
        raise ValueError(f"{field_name}_must_be_sha256")


@dataclass(frozen=True)
class IncidentPackInstallPermitReceipt:
    """Owner-authorized exact non-structural pack install during an open incident."""

    permit_id: str
    capability_code: str
    current_version: str
    candidate_version: str
    artifact_sha256: str
    allowed_operation_keys: tuple[str, ...]
    preflight_evidence_paths: tuple[str, ...]
    migration_revisions: tuple[str, ...]
    migration_files_digest: str
    schema_mutation_required: bool
    backout_install_id: str
    backout_artifact_sha256: str
    expires_at: str
    owner: str
    owner_authorization: str

    def validate(self) -> None:
        missing = _required_text(
            {
                "permit_id": self.permit_id,
                "capability_code": self.capability_code,
                "current_version": self.current_version,
                "candidate_version": self.candidate_version,
                "artifact_sha256": self.artifact_sha256,
                "migration_files_digest": self.migration_files_digest,
                "backout_install_id": self.backout_install_id,
                "backout_artifact_sha256": self.backout_artifact_sha256,
                "expires_at": self.expires_at,
                "owner": self.owner,
                "owner_authorization": self.owner_authorization,
            }
        )
        if not self.preflight_evidence_paths or any(
            not str(path).strip() for path in self.preflight_evidence_paths
        ):
            missing.append("preflight_evidence_paths")
        if not self.migration_revisions or any(
            not str(revision).strip() for revision in self.migration_revisions
        ):
            missing.append("migration_revisions")
        if missing:
            raise ValueError(
                "Pack install permit is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )
        if self.schema_mutation_required:
            raise ValueError("pack_install_permit_forbids_schema_mutation")
        _validate_sha256(self.artifact_sha256, field_name="artifact_sha256")
        _validate_sha256(
            self.migration_files_digest,
            field_name="migration_files_digest",
        )
        _validate_sha256(
            self.backout_artifact_sha256,
            field_name="backout_artifact_sha256",
        )
        artifact_sha256 = self.artifact_sha256.strip().lower()
        required_keys = {
            f"capability_install_intake:file@sha256:{artifact_sha256}",
            f"capability_install_job@sha256:{artifact_sha256}",
        }
        if set(self.allowed_operation_keys) != required_keys:
            raise ValueError("pack_install_permit_operation_keys_must_be_exact")
        if len(self.allowed_operation_keys) != len(required_keys):
            raise ValueError("pack_install_permit_operation_keys_must_be_unique")
        _parse_timestamp(self.expires_at, field_name="pack_install_permit_expires_at")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["allowed_operation_keys"] = list(self.allowed_operation_keys)
        payload["preflight_evidence_paths"] = list(self.preflight_evidence_paths)
        payload["migration_revisions"] = list(self.migration_revisions)
        return payload


@dataclass(frozen=True)
class IncidentTargetedMigrationPermitReceipt:
    """Owner-authorized exact create-only migration during an open incident."""

    permit_id: str
    alembic_config_name: str
    revision: str
    migration_file_sha256: str
    migration_mode: str
    created_relations: tuple[str, ...]
    allowed_operation_key: str
    preflight_evidence_paths: tuple[str, ...]
    expires_at: str
    owner: str
    owner_authorization: str

    def validate(self) -> None:
        missing = _required_text(
            {
                "permit_id": self.permit_id,
                "alembic_config_name": self.alembic_config_name,
                "revision": self.revision,
                "migration_file_sha256": self.migration_file_sha256,
                "migration_mode": self.migration_mode,
                "allowed_operation_key": self.allowed_operation_key,
                "expires_at": self.expires_at,
                "owner": self.owner,
                "owner_authorization": self.owner_authorization,
            }
        )
        if not self.created_relations or any(
            not str(relation).strip() for relation in self.created_relations
        ):
            missing.append("created_relations")
        if not self.preflight_evidence_paths or any(
            not str(path).strip() for path in self.preflight_evidence_paths
        ):
            missing.append("preflight_evidence_paths")
        if missing:
            raise ValueError(
                "Targeted migration permit is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )
        _validate_sha256(
            self.migration_file_sha256,
            field_name="migration_file_sha256",
        )
        if self.migration_mode != "create_only":
            raise ValueError("targeted_migration_permit_requires_create_only")
        expected_operation_key = (
            f"alembic_upgrade:{self.alembic_config_name}:{self.revision}"
        )
        if self.allowed_operation_key != expected_operation_key:
            raise ValueError("targeted_migration_permit_operation_key_must_be_exact")
        for relation in self.created_relations:
            normalized = str(relation).strip()
            if "*" in normalized or any(character.isspace() for character in normalized):
                raise ValueError("targeted_migration_permit_relations_must_be_exact")
        _parse_timestamp(
            self.expires_at,
            field_name="targeted_migration_permit_expires_at",
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["created_relations"] = list(self.created_relations)
        payload["preflight_evidence_paths"] = list(self.preflight_evidence_paths)
        return payload


@dataclass(frozen=True)
class IncidentCloseReceipt:
    """Evidence required before an incident may be closed."""

    deep_trigger_classification: str
    deep_trigger_event_sha256: str
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
            "deep_trigger_classification": self.deep_trigger_classification,
            "deep_trigger_event_sha256": self.deep_trigger_event_sha256,
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
                "Incident close receipt is missing required fields: "
                + ", ".join(sorted(set(missing)))
            )
        classification = self.deep_trigger_classification.strip().lower()
        forbidden = ("unknown", "unattributed", "undetermined", "unresolved")
        if any(marker in classification for marker in forbidden):
            raise ValueError("incident_close_requires_attributed_deep_trigger")
        if not re.fullmatch(r"[0-9a-f]{40}", self.fix_commit):
            raise ValueError("incident_close_fix_commit_must_be_exact")
        for field_name, value in {
            "deep_trigger_event_sha256": self.deep_trigger_event_sha256,
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
            raise ValueError("incident_close_requires_restore_evidence")
        boundaries = self.soak_window.split("/")
        if len(boundaries) != 2:
            raise ValueError("incident_close_soak_window_invalid")
        soak_started_at = _parse_timestamp(
            boundaries[0],
            field_name="incident_close_soak_started_at",
        )
        soak_ended_at = _parse_timestamp(
            boundaries[1],
            field_name="incident_close_soak_ended_at",
        )
        if soak_ended_at <= soak_started_at:
            raise ValueError("incident_close_soak_window_invalid")
        if soak_ended_at > datetime.now(timezone.utc):
            raise ValueError("incident_close_soak_window_not_complete")

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
    diagnostic_permit: Optional[Mapping[str, Any]] = None
    containment_receipt: Optional[Mapping[str, Any]] = None
    pack_install_permits: tuple[Mapping[str, Any], ...] = ()
    targeted_migration_permits: tuple[Mapping[str, Any], ...] = ()
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
            diagnostic_permit=payload.get("diagnostic_permit"),
            containment_receipt=payload.get("containment_receipt"),
            pack_install_permits=tuple(payload.get("pack_install_permits") or ()),
            targeted_migration_permits=tuple(
                payload.get("targeted_migration_permits") or ()
            ),
            close_receipt=payload.get("close_receipt"),
        )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["state"] = self.state.value
        if self.diagnostic_permit is None:
            payload.pop("diagnostic_permit", None)
        if self.containment_receipt is None:
            payload.pop("containment_receipt", None)
        if self.pack_install_permits:
            payload["pack_install_permits"] = list(self.pack_install_permits)
        else:
            payload.pop("pack_install_permits", None)
        if self.targeted_migration_permits:
            payload["targeted_migration_permits"] = list(
                self.targeted_migration_permits
            )
        else:
            payload.pop("targeted_migration_permits", None)
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
