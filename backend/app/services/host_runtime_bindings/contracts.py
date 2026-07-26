"""Strict commands and projections for host runtime binding authority."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)


Digest = str
BindingDesiredState = Literal[
    "declared",
    "materialized",
    "active",
    "degraded",
    "retiring",
    "retired",
]
ConditionStatus = Literal["true", "false", "unknown"]
ConditionType = Literal[
    "Materialized",
    "RuntimeDigestVerified",
    "SupervisorReady",
    "PermissionsReady",
    "ResourceLaneReady",
]
GrantStatus = Literal["active", "revoked", "expired"]
HostOperation = Annotated[
    str,
    StringConstraints(pattern=r"^[a-z][a-z0-9_.-]{1,63}$"),
]
REQUIRED_CONDITION_TYPES = frozenset(
    {
        "Materialized",
        "RuntimeDigestVerified",
        "SupervisorReady",
        "PermissionsReady",
        "ResourceLaneReady",
    }
)


class HostRuntimeCondition(BaseModel):
    type: ConditionType
    status: ConditionStatus
    reason: str = Field(min_length=1, max_length=128)
    observed_generation: int = Field(ge=1)
    observed_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def require_timezone(self):
        if self.observed_at.tzinfo is None:
            raise ValueError("condition_observed_at_must_be_timezone_aware")
        return self


class DeclareBindingCommand(BaseModel):
    device_id: str = Field(min_length=1, max_length=128)
    capability_code: str = Field(pattern=r"^[a-z0-9_]{2,128}$")
    requirement_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    runtime_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    host_assets_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    entrypoint: str = Field(pattern=r"^scripts/[a-zA-Z0-9_./-]+\.py$")
    entrypoint_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    share_policy: Literal["exclusive_workspace", "workspace_grants"]
    operations: list[HostOperation] = Field(min_length=1, max_length=32)
    permission_classes: list[str] = Field(min_length=1, max_length=16)
    resource_lane: str = Field(pattern=r"^host\.[a-z0-9_.-]+$")
    expected_generation: int = Field(ge=0)

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_unique_values(self):
        if ".." in self.entrypoint.split("/"):
            raise ValueError("binding_entrypoint_path_invalid")
        if self.runtime_digest != self.host_assets_digest:
            raise ValueError("binding_runtime_digest_must_match_host_assets")
        if len(self.operations) != len(set(self.operations)):
            raise ValueError("binding_operations_must_be_unique")
        if len(self.permission_classes) != len(set(self.permission_classes)):
            raise ValueError("binding_permission_classes_must_be_unique")
        return self


class MaterializationReceiptCommand(BaseModel):
    binding_id: str = Field(min_length=1, max_length=64)
    generation: int = Field(ge=1)
    runtime_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    host_assets_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    installed_tree_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    archive_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    source_commit: str = Field(pattern=r"^[0-9a-f]{40}$|^[0-9a-f]{64}$")
    builder_id: str = Field(min_length=1, max_length=128)
    materialized_root: str = Field(min_length=1, max_length=1024)

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_runtime_identity(self):
        if not (
            self.runtime_digest
            == self.host_assets_digest
            == self.installed_tree_digest
        ):
            raise ValueError("host_materialization_runtime_identity_mismatch")
        return self


class AttestBindingCommand(BaseModel):
    binding_id: str = Field(min_length=1, max_length=64)
    generation: int = Field(ge=1)
    runtime_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    executor_identity_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    permission_revision: int = Field(ge=1)
    conditions: list[HostRuntimeCondition] = Field(min_length=1, max_length=16)
    observed_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_attestation(self):
        if self.observed_at.tzinfo is None:
            raise ValueError("attestation_observed_at_must_be_timezone_aware")
        condition_types = [condition.type for condition in self.conditions]
        if len(condition_types) != len(set(condition_types)):
            raise ValueError("attestation_condition_types_must_be_unique")
        if set(condition_types) != REQUIRED_CONDITION_TYPES:
            raise ValueError("attestation_condition_types_incomplete")
        if any(
            condition.observed_generation != self.generation
            for condition in self.conditions
        ):
            raise ValueError("attestation_condition_generation_mismatch")
        return self


class GrantWorkspaceCommand(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    binding_id: str = Field(min_length=1, max_length=64)
    binding_generation: int = Field(ge=1)
    operation: HostOperation
    operation_args_sha256: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    policy_revision: int = Field(ge=1)
    attestation_revision: int = Field(ge=1)
    expires_at: datetime
    provider_code: str | None = Field(
        default=None,
        pattern=r"^[a-z0-9_.-]{1,128}$",
    )
    voice_profile_id: str | None = Field(default=None, min_length=1, max_length=128)
    reference_rights_revision: int | None = Field(default=None, ge=1)

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_expiry(self):
        if self.expires_at.tzinfo is None:
            raise ValueError("grant_expires_at_must_be_timezone_aware")
        voice_values = (
            self.provider_code,
            self.voice_profile_id,
            self.reference_rights_revision,
        )
        if any(value is not None for value in voice_values) and not all(
            value is not None for value in voice_values
        ):
            raise ValueError("grant_voice_scope_must_be_complete")
        return self


class RequestBindingRetirementCommand(BaseModel):
    binding_id: str = Field(min_length=1, max_length=64)
    generation: int = Field(ge=1)
    reason: str = Field(
        min_length=1,
        max_length=128,
        pattern=r"^[a-z][a-z0-9_.-]{1,127}$",
    )

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class FinalizeBindingRetirementCommand(BaseModel):
    binding_id: str = Field(min_length=1, max_length=64)
    generation: int = Field(ge=1)
    supervisor_cleanup_terminal: Literal[True]

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )


class HostRuntimeAttestationProjection(BaseModel):
    revision: int = Field(ge=1)
    observed_generation: int = Field(ge=1)
    runtime_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    executor_identity_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    permission_revision: int = Field(ge=1)
    conditions: list[HostRuntimeCondition]
    observed_at: datetime

    model_config = ConfigDict(extra="forbid", strict=True)


class WorkspaceHostGrantProjection(BaseModel):
    grant_id: str
    workspace_id: str
    binding_id: str
    binding_generation: int = Field(ge=1)
    operation: HostOperation
    operation_args_sha256: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    policy_revision: int = Field(ge=1)
    attestation_revision: int = Field(ge=1)
    expires_at: datetime
    status: GrantStatus
    provider_code: str | None = None
    voice_profile_id: str | None = None
    reference_rights_revision: int | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class DeviceHostBindingProjection(BaseModel):
    binding_id: str
    device_id: str
    capability_code: str
    requirement_code: str
    capability_version: str
    runtime_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    host_assets_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    entrypoint: str = Field(pattern=r"^scripts/[a-zA-Z0-9_./-]+\.py$")
    entrypoint_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    desired_state: BindingDesiredState
    generation: int = Field(ge=1)
    observed_generation: int | None = Field(default=None, ge=1)
    share_policy: Literal["exclusive_workspace", "workspace_grants"]
    operations: list[HostOperation]
    permission_classes: list[str]
    resource_lane: str
    materialized_root: str | None = None
    finalizers: list[str] = Field(default_factory=list)
    attestation: HostRuntimeAttestationProjection | None = None

    model_config = ConfigDict(extra="forbid", strict=True)


class EffectiveHostAdmissionProjection(BaseModel):
    admitted: bool
    workspace_id: str
    binding_id: str | None = None
    binding_generation: int | None = Field(default=None, ge=1)
    operation: HostOperation
    grant_id: str | None = None
    attestation_revision: int | None = Field(default=None, ge=1)
    policy_revision: int | None = Field(default=None, ge=1)
    blockers: list[str] = Field(default_factory=list, max_length=20)

    model_config = ConfigDict(extra="forbid", strict=True)


class HostRuntimeCommandReceipt(BaseModel):
    command: Literal[
        "declare",
        "materialize",
        "attest",
        "grant",
        "revoke",
        "retire",
    ]
    binding_id: str | None = None
    grant_id: str | None = None
    generation: int | None = Field(default=None, ge=1)
    revision: int | None = Field(default=None, ge=1)
    accepted: Literal[True] = True

    model_config = ConfigDict(extra="forbid", strict=True)


class HostRuntimeExecutionPermitClaims(BaseModel):
    schema_version: Literal["mindscape.host-runtime-execution-permit.v1"]
    workspace_id: str = Field(min_length=1, max_length=128)
    binding_id: str = Field(min_length=1, max_length=64)
    binding_generation: int = Field(ge=1)
    capability_code: str = Field(pattern=r"^[a-z0-9_]{2,128}$")
    requirement_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,63}$")
    capability_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    operation: HostOperation
    operation_args_sha256: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    grant_id: str = Field(min_length=1, max_length=64)
    attestation_revision: int = Field(ge=1)
    policy_revision: int = Field(ge=1)
    runtime_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    host_assets_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    entrypoint: str = Field(pattern=r"^scripts/[a-zA-Z0-9_./-]+\.py$")
    entrypoint_digest: Digest = Field(pattern=r"^[0-9a-f]{64}$")
    materialized_root: str = Field(min_length=1, max_length=1024)
    permission_classes: list[str] = Field(min_length=1, max_length=16)
    resource_lane: str = Field(pattern=r"^host\.[a-z0-9_.-]+$")
    provider_code: str | None = None
    voice_profile_id: str | None = None
    reference_rights_revision: int | None = Field(default=None, ge=1)
    issued_at: datetime
    expires_at: datetime

    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        str_strip_whitespace=True,
    )

    @model_validator(mode="after")
    def validate_execution_claims(self):
        if (
            self.issued_at.tzinfo is None
            or self.expires_at.tzinfo is None
            or self.expires_at <= self.issued_at
        ):
            raise ValueError("host_execution_permit_time_invalid")
        if ".." in self.entrypoint.split("/"):
            raise ValueError("host_execution_permit_entrypoint_invalid")
        voice_values = (
            self.provider_code,
            self.voice_profile_id,
            self.reference_rights_revision,
        )
        if any(value is not None for value in voice_values) and not all(
            value is not None for value in voice_values
        ):
            raise ValueError("host_execution_permit_voice_scope_incomplete")
        return self


class HostRuntimeExecutionPermit(BaseModel):
    claims: HostRuntimeExecutionPermitClaims
    signature: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", strict=True)


class HostRuntimeExecutionPermitRequest(BaseModel):
    operation_args: list[str] = Field(default_factory=list, max_length=64)
    ttl_seconds: int = Field(default=60, ge=1, le=60)

    model_config = ConfigDict(extra="forbid", strict=True)

    @model_validator(mode="after")
    def validate_operation_args(self):
        if any(
            "\x00" in value or len(value) > 1024
            for value in self.operation_args
        ):
            raise ValueError("host_execution_operation_args_invalid")
        return self
