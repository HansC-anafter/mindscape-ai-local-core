"""Strict row-to-contract projection for host binding authority."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .contracts import (
    DeviceHostBindingProjection,
    HostRuntimeAttestationProjection,
    WorkspaceHostGrantProjection,
)


def binding_from_record(record: dict[str, Any]) -> DeviceHostBindingProjection:
    attestation_record = record.get("attestation")
    attestation = (
        HostRuntimeAttestationProjection.model_validate(
            _normalize_attestation_record(attestation_record)
        )
        if isinstance(attestation_record, dict)
        else None
    )
    return DeviceHostBindingProjection.model_validate(
        {
            "binding_id": record["id"],
            "device_id": record["device_id"],
            "capability_code": record["capability_code"],
            "requirement_code": record["requirement_code"],
            "capability_version": record["capability_version"],
            "runtime_digest": record["runtime_digest"],
            "host_assets_digest": record["host_assets_digest"],
            "entrypoint": record["entrypoint"],
            "entrypoint_digest": record["entrypoint_digest"],
            "desired_state": record["desired_state"],
            "generation": record["generation"],
            "observed_generation": (
                attestation.observed_generation if attestation else None
            ),
            "share_policy": record["share_policy"],
            "operations": record["operations"],
            "permission_classes": record["permission_classes"],
            "resource_lane": record["resource_lane"],
            "materialized_root": record.get("materialized_root"),
            "finalizers": record.get("finalizers") or [],
            "attestation": attestation,
        }
    )


def grant_from_record(
    record: dict[str, Any],
    *,
    now: datetime | None = None,
) -> WorkspaceHostGrantProjection:
    observed_now = now or datetime.now(timezone.utc)
    status = record["status"]
    expires_at = _aware_datetime(record["expires_at"])
    if status == "active" and expires_at <= observed_now:
        status = "expired"
    return WorkspaceHostGrantProjection.model_validate(
        {
            "grant_id": record["id"],
            "workspace_id": record["workspace_id"],
            "binding_id": record["binding_id"],
            "binding_generation": record["binding_generation"],
            "operation": record["operation"],
            "operation_args_sha256": record["operation_args_sha256"],
            "policy_revision": record["policy_revision"],
            "attestation_revision": record["attestation_revision"],
            "expires_at": expires_at,
            "status": status,
            "provider_code": record.get("provider_code"),
            "voice_profile_id": record.get("voice_profile_id"),
            "reference_rights_revision": record.get(
                "reference_rights_revision"
            ),
        }
    )


def _normalize_attestation_record(
    record: dict[str, Any],
) -> dict[str, Any]:
    conditions = record.get("conditions")
    if not isinstance(conditions, list):
        raise ValueError("host_attestation_conditions_invalid")
    normalized_conditions = []
    for condition in conditions:
        if not isinstance(condition, dict):
            raise ValueError("host_attestation_condition_invalid")
        normalized_conditions.append(
            {
                **condition,
                "observed_at": _aware_datetime(condition.get("observed_at")),
            }
        )
    return {
        **record,
        "conditions": normalized_conditions,
        "observed_at": _aware_datetime(record.get("observed_at")),
    }


def _aware_datetime(value: Any) -> datetime:
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("host_projection_datetime_invalid")
    return value
