"""Local Core contracts for CRS external execution authorization."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


SHA256_PATTERN = r"^[0-9a-f]{64}$"


class ExternalCapabilityRef(BaseModel):
    capability_key: str = Field(min_length=1, max_length=256)
    operation_type: Literal[
        "query",
        "read",
        "generate",
        "modify",
        "delete",
        "publish",
        "payment",
    ]

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @property
    def canonical_ref(self) -> str:
        return f"{self.capability_key}#{self.operation_type}"


class ExternalPackRef(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)
    source_sha256: str = Field(pattern=SHA256_PATTERN)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @property
    def canonical_ref(self) -> str:
        return f"{self.provider}:{self.code}@{self.version}#{self.source_sha256}"


class ExternalExecutionAuthorizationRequest(BaseModel):
    source_runtime_id: str = Field(min_length=2, max_length=128)
    workspace_id: str = Field(min_length=1, max_length=128)
    active_group_id: str = Field(min_length=1, max_length=128)
    topology_snapshot_id: str = Field(min_length=1, max_length=128)
    topology_snapshot_hash: str = Field(pattern=SHA256_PATTERN)
    wpcs_hash: str = Field(pattern=SHA256_PATTERN)
    catalog_hash: str = Field(pattern=SHA256_PATTERN)
    product_surface_id: str = Field(min_length=2, max_length=256)
    exact_capability_closure: list[ExternalCapabilityRef] = Field(
        min_length=1,
        max_length=64,
    )
    exact_pack_closure: list[ExternalPackRef] = Field(
        min_length=1,
        max_length=64,
    )
    deployment_mode: Literal["unmanaged_local", "provider_managed"]
    dce_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    trace_id: str = Field(min_length=1, max_length=128)
    root_execution_id: str = Field(min_length=1, max_length=128)
    request_deadline: datetime

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_exact_context(self):
        capabilities = [
            item.canonical_ref for item in self.exact_capability_closure
        ]
        packs = [item.canonical_ref for item in self.exact_pack_closure]
        if capabilities != sorted(set(capabilities)):
            raise ValueError(
                "exact_capability_closure_must_be_unique_and_sorted"
            )
        if packs != sorted(set(packs)):
            raise ValueError("exact_pack_closure_must_be_unique_and_sorted")
        if self.deployment_mode == "provider_managed":
            if self.dce_hash is None:
                raise ValueError("provider_managed_requires_dce_hash")
        elif self.dce_hash is not None:
            raise ValueError("unmanaged_local_cannot_include_dce_hash")
        if self.request_deadline.tzinfo is None:
            raise ValueError("request_deadline_must_be_timezone_aware")
        return self


class RiskDecision(BaseModel):
    max_risk_score: int = Field(ge=0)
    checked_capability_keys: list[str]

    model_config = ConfigDict(extra="forbid")


class QuotaDecision(BaseModel):
    daily_remaining: int | None = None
    monthly_remaining: int | None = None
    lease_expires_at: datetime

    model_config = ConfigDict(extra="forbid")


class ProviderDecision(BaseModel):
    provider_name: str
    api_url: str
    token_type: str
    access_token: str
    token_id: str
    token_expires_at: datetime

    model_config = ConfigDict(extra="forbid")


class ExternalExecutionDecisionClaims(BaseModel):
    media_type: Literal[
        "application/vnd.mindscape.external-execution-decision.v1+json"
    ]
    schema_version: Literal["mindscape.external-execution-decision.v1"]
    issuer: str
    audience: str
    decision_id: str
    allowed: bool
    deny_code: str | None = None
    source_runtime_id: str
    workspace_id: str
    active_group_id: str
    topology_snapshot_id: str
    topology_snapshot_hash: str = Field(pattern=SHA256_PATTERN)
    wpcs_hash: str = Field(pattern=SHA256_PATTERN)
    catalog_hash: str = Field(pattern=SHA256_PATTERN)
    product_surface_id: str
    exact_capability_closure: list[ExternalCapabilityRef]
    exact_pack_closure: list[ExternalPackRef]
    deployment_mode: Literal["unmanaged_local", "provider_managed"]
    dce_hash: str | None = Field(default=None, pattern=SHA256_PATTERN)
    risk: RiskDecision | None = None
    quota: QuotaDecision | None = None
    provider: ProviderDecision | None = None
    trace_id: str
    root_execution_id: str
    issued_at: datetime
    expires_at: datetime

    model_config = ConfigDict(extra="forbid")

    @model_validator(mode="after")
    def validate_outcome_shape(self):
        if self.allowed:
            if self.deny_code is not None:
                raise ValueError("allowed_decision_cannot_include_deny_code")
            if self.risk is None or self.quota is None or self.provider is None:
                raise ValueError("allowed_decision_requires_all_policy_results")
        elif self.deny_code is None:
            raise ValueError("denied_decision_requires_deny_code")
        return self


class SignedExternalExecutionDecision(BaseModel):
    claims: ExternalExecutionDecisionClaims
    alg: Literal["EdDSA"]
    kid: str
    signature: str

    model_config = ConfigDict(extra="forbid")


class ExternalExecutionAuthorizationResponse(BaseModel):
    decision: SignedExternalExecutionDecision

    model_config = ConfigDict(extra="forbid")
