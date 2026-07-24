"""Portable Deployment Capability Envelope and local state contracts."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DeploymentControlMode = Literal["unmanaged_local", "provider_managed"]


class EnvelopePackRef(BaseModel):
    provider: str = Field(min_length=1, max_length=64)
    code: str = Field(min_length=1, max_length=128)
    version: str = Field(min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @property
    def canonical_ref(self) -> str:
        return f"{self.provider}:{self.code}@{self.version}"


class EnvelopeProductGrant(BaseModel):
    pcs_id: str = Field(min_length=2, max_length=128)
    pcs_version: str = Field(min_length=1, max_length=64)
    surface_ids: list[str] = Field(min_length=1, max_length=64)
    pack_closure: list[EnvelopePackRef] = Field(min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_unique_sorted_values(self):
        if self.surface_ids != sorted(set(self.surface_ids)):
            raise ValueError("surface_ids_must_be_unique_and_sorted")
        pack_refs = [item.canonical_ref for item in self.pack_closure]
        if pack_refs != sorted(set(pack_refs)):
            raise ValueError("pack_closure_must_be_unique_and_sorted")
        return self


class DeploymentCapabilityEnvelopeClaims(BaseModel):
    media_type: Literal[
        "application/vnd.mindscape.deployment-capability-envelope.v1+json"
    ]
    schema_version: Literal["mindscape.deployment-capability-envelope.v1"]
    issuer: str = Field(min_length=2, max_length=128)
    audience: str = Field(min_length=2, max_length=256)
    provider_code: str = Field(min_length=2, max_length=64)
    source_runtime_id: str = Field(min_length=2, max_length=128)
    tenant_id: str = Field(min_length=1, max_length=128)
    site_id: str = Field(min_length=1, max_length=128)
    catalog_hash: str = Field(pattern="^[0-9a-f]{64}$")
    issued_at: datetime
    not_before: datetime
    expires_at: datetime
    envelope_revision: int = Field(ge=1)
    allowed_products: list[EnvelopeProductGrant] = Field(
        min_length=1,
        max_length=64,
    )

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_products(self):
        identities = [
            (product.pcs_id, product.pcs_version)
            for product in self.allowed_products
        ]
        if identities != sorted(set(identities)):
            raise ValueError("allowed_products_must_be_unique_and_sorted")
        return self


class SignedDeploymentCapabilityEnvelope(BaseModel):
    claims: DeploymentCapabilityEnvelopeClaims
    alg: Literal["EdDSA"]
    kid: str = Field(min_length=2, max_length=128)
    signature: str = Field(min_length=80, max_length=128)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReplaceDeploymentControlCommand(BaseModel):
    expected_state_revision: int = Field(ge=0)
    mode: DeploymentControlMode
    provider_code: str | None = Field(default=None, min_length=2, max_length=64)
    signed_envelope: SignedDeploymentCapabilityEnvelope | None = None

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_mode_shape(self):
        if self.mode == "unmanaged_local":
            if self.provider_code is not None or self.signed_envelope is not None:
                raise ValueError("unmanaged_local_cannot_include_provider_envelope")
            return self
        if self.provider_code is None or self.signed_envelope is None:
            raise ValueError("provider_managed_requires_provider_envelope")
        if self.provider_code != self.signed_envelope.claims.provider_code:
            raise ValueError("provider_code_envelope_mismatch")
        return self


class DeploymentControlState(BaseModel):
    mode: DeploymentControlMode
    provider_code: str | None = None
    signed_envelope: SignedDeploymentCapabilityEnvelope | None = None
    envelope_hash: str | None = None
    issuer: str | None = None
    key_id: str | None = None
    expires_at: datetime | None = None
    envelope_revision: int | None = None
    state_revision: int = Field(ge=0)
    updated_at: datetime | None = None
    updated_by: str | None = None


class DeploymentControlReplaceResult(BaseModel):
    state: DeploymentControlState
    replaced: bool


class CeilingAssignment(BaseModel):
    pcs_id: str
    pcs_version: str
    allowed_surface_ids: list[str]


class EffectiveDeploymentCeiling(BaseModel):
    mode: DeploymentControlMode
    provider_code: str | None
    state_revision: int
    envelope_revision: int | None
    envelope_hash: str | None
    assignments: list[CeilingAssignment]
