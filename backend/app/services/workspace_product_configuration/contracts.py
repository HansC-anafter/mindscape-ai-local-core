"""Typed contracts for Product Capability Set configuration and projection."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


ScopeKind = Literal["workspace", "workspace_group"]
AdmissionMode = Literal[
    "legacy_unmanaged",
    "configuration_only",
    "shadow",
    "enforced",
]
PersistedAdmissionMode = Literal[
    "configuration_only",
    "shadow",
    "enforced",
]


class ProductAssignment(BaseModel):
    pcs_id: str = Field(min_length=2, max_length=128)
    pcs_version: str = Field(min_length=5, max_length=64)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ReplaceScopeCommand(BaseModel):
    expected_revision: int = Field(ge=0)
    assignments: list[ProductAssignment] = Field(default_factory=list, max_length=64)
    admission_mode: Optional[PersistedAdmissionMode] = None
    catalog_hash: str = Field(min_length=64, max_length=64)

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @model_validator(mode="after")
    def validate_unique_products(self):
        ids = [assignment.pcs_id for assignment in self.assignments]
        if len(ids) != len(set(ids)):
            raise ValueError("duplicate product assignment")
        return self


class ScopeConfiguration(BaseModel):
    scope_kind: ScopeKind
    scope_id: str
    catalog_hash: Optional[str] = None
    revision: int = Field(ge=0)
    admission_mode: Optional[AdmissionMode] = None
    assignments: list[ProductAssignment] = Field(default_factory=list)
    editable: bool


class ProductClosureSummary(BaseModel):
    total_packs: int = Field(ge=0)
    exact_ready_packs: int = Field(ge=0)
    missing_packs: int = Field(ge=0)
    disabled_packs: int = Field(ge=0)
    version_mismatch_packs: int = Field(ge=0)


class AvailableProduct(BaseModel):
    pcs_id: str
    exact_version: str
    display_name: str
    outcome_summary: str
    surface_ids: list[str] = Field(default_factory=list)
    closure_summary: ProductClosureSummary


class EffectiveProductAssignment(BaseModel):
    pcs_id: str
    pcs_version: str
    product_surface_ids: list[str] = Field(default_factory=list)
    configuration_sources: list[ScopeKind] = Field(default_factory=list)
    host_ready: bool


class WorkspaceCapabilitySetSnapshot(BaseModel):
    source_runtime_id: str
    workspace_id: str
    explicit_active_group_id: Optional[str] = None
    topology_revision: Optional[int] = None
    topology_content_hash: Optional[str] = None
    catalog_hash: str
    snapshot_hash: str
    workspace_scope_revision: int = Field(ge=0)
    group_scope_revision: int = Field(ge=0)
    workspace_admission_mode: AdmissionMode
    editable_scopes: list[ScopeKind]
    scope_configurations: list[ScopeConfiguration]
    available_products: list[AvailableProduct]
    effective_assignments: list[EffectiveProductAssignment]
    configuration_errors: list[str] = Field(default_factory=list, max_length=20)


class CatalogImportResult(BaseModel):
    artifact_hash: str
    catalog_hash: str
    source_commit: str
    compiler_version: str
    status: Literal["active"] = "active"
    imported: bool


class CatalogArtifactEnvelope(BaseModel):
    media_type: Literal[
        "application/vnd.mindscape.product-capability-catalog.v1+json"
    ]
    schema_version: Literal["mindscape.product-capability-catalog.v1"]
    catalog_hash: str = Field(pattern="^[0-9a-f]{64}$")
    artifact_hash: str = Field(pattern="^[0-9a-f]{64}$")
    source_commit: str = Field(pattern="^[0-9a-f]{40}$|^[0-9a-f]{64}$")
    compiler_version: str = Field(min_length=1, max_length=32)
    generated_by: str = Field(min_length=1, max_length=128)
    catalog: dict[str, Any]

    model_config = ConfigDict(extra="forbid")
