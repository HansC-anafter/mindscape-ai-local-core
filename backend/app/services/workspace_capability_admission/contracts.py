"""Typed root/child contracts for workspace capability admission."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .external_execution_contracts import ExternalExecutionDecisionClaims


SelectorKind = Literal["api_prefix", "tool", "playbook"]
OperationType = Literal[
    "query",
    "read",
    "generate",
    "modify",
    "delete",
    "publish",
    "payment",
]
AdmissionEntry = Literal["local", "remote"]
ExecutionBackend = Literal["local", "external_provider"]
AdmissionAvailability = Literal[
    "available",
    "not_configured",
    "configuration_conflict",
    "capability_not_permitted",
    "not_installed",
    "dependency_not_ready",
    "deployment_not_permitted",
    "remote_not_exposed",
    "external_authorization_unavailable",
]


class RootAdmissionRequest(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=128)
    explicit_active_group_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=128,
    )
    observed_topology_revision: int | None = Field(default=None, ge=1)
    product_surface_id: str | None = Field(
        default=None,
        min_length=2,
        max_length=256,
    )
    selector_kind: SelectorKind
    selector_key: str = Field(min_length=1, max_length=512)
    operation_type: OperationType
    entry: AdmissionEntry
    remote_ingress_verified: bool = False
    execution_backend: ExecutionBackend
    actor_user_id: str = Field(min_length=1, max_length=128)
    allowed_workspace_ids: list[str] = Field(default_factory=list, max_length=256)
    allowed_group_ids: list[str] = Field(default_factory=list, max_length=256)
    trace_id: str = Field(min_length=1, max_length=128)
    root_execution_id: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_remote_evidence(self):
        if self.entry == "local" and self.remote_ingress_verified:
            raise ValueError("local_entry_cannot_include_remote_ingress")
        return self


class ExecutionAdmissionSnapshot(BaseModel):
    media_type: Literal[
        "application/vnd.mindscape.execution-admission-snapshot.v1+json"
    ]
    schema_version: Literal["mindscape.execution-admission-snapshot.v1"]
    source_runtime_id: str
    workspace_id: str
    active_group_id: str | None = None
    topology_revision: int | None = Field(default=None, ge=1)
    topology_snapshot_id: str | None = None
    topology_snapshot_hash: str | None = Field(
        default=None,
        pattern=r"^[0-9a-f]{64}$",
    )
    wpcs_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    catalog_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    admission_mode: Literal[
        "legacy_unmanaged",
        "configuration_only",
        "shadow",
        "enforced",
    ]
    pcs_id: str | None = None
    pcs_version: str | None = None
    product_surface_id: str
    selector_kind: SelectorKind
    selector_key: str
    operation_type: OperationType
    entry: AdmissionEntry
    execution_backend: ExecutionBackend
    deployment_mode: Literal["unmanaged_local", "provider_managed"]
    deployment_state_revision: int = Field(ge=0)
    deployment_envelope_revision: int | None = Field(default=None, ge=1)
    dce_hash: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    availability: AdmissionAvailability
    diagnostics: list[str] = Field(default_factory=list, max_length=20)
    external_decision_id: str | None = None
    external_decision_issuer: str | None = None
    external_decision_expires_at: datetime | None = None
    provider_token_id: str | None = None
    trace_id: str
    root_execution_id: str
    admitted_at: datetime
    snapshot_hash: str = Field(pattern=r"^[0-9a-f]{64}$")

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_snapshot_shape(self):
        topology_values = (
            self.active_group_id,
            self.topology_revision,
            self.topology_snapshot_id,
            self.topology_snapshot_hash,
        )
        if any(topology_values) and not all(topology_values):
            raise ValueError("topology_snapshot_fields_must_be_complete")
        if self.deployment_mode == "provider_managed":
            if self.dce_hash is None:
                raise ValueError("provider_managed_requires_dce_hash")
        elif self.dce_hash is not None:
            raise ValueError("unmanaged_local_cannot_include_dce_hash")
        external_values = (
            self.external_decision_id,
            self.external_decision_issuer,
            self.external_decision_expires_at,
            self.provider_token_id,
        )
        if self.execution_backend == "external_provider":
            if not all(external_values):
                raise ValueError("external_backend_requires_verified_decision")
        elif any(external_values):
            raise ValueError("local_backend_cannot_include_external_decision")
        if self.admitted_at.tzinfo is None:
            raise ValueError("admitted_at_must_be_timezone_aware")
        return self


@dataclass(frozen=True)
class RootPrincipalEvidence:
    """Internal-only identity projection used to build transient contexts."""

    workspace_id: str
    actor_user_id: str
    allowed_workspace_ids: tuple[str, ...]
    allowed_group_ids: tuple[str, ...]
    workspace_owner_user_id: str | None
    group_owner_user_id: str | None


@dataclass(frozen=True)
class RootAdmissionResult:
    """Snapshot is persistable; external decision remains transient."""

    snapshot: ExecutionAdmissionSnapshot
    external_decision: ExternalExecutionDecisionClaims | None = None
    active_group_context: Any | None = None
    topology_snapshot: Any | None = None
    principal_evidence: RootPrincipalEvidence | None = None


class AdmissionDenied(RuntimeError):
    def __init__(self, code: AdmissionAvailability) -> None:
        super().__init__(code)
        self.code = code
