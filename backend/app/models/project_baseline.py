"""Project Baseline models for collaboration."""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class ProjectBaseline(BaseModel):
    """
    Project Baseline - Common ground for collaboration.

    Defines the shared constraints and standards that all participants
    must respect, regardless of their personal capability packs.
    """
    workspace_id: str = Field(..., description="Workspace ID")
    project_id: Optional[str] = Field(None, description="Project ID (if applicable)")

    # Policy constraints
    policy_set_id: Optional[str] = Field(
        None,
        description="Policy set ID (brand guidelines, compliance rules)"
    )

    # Delivery standards
    delivery_schema_ref: Optional[str] = Field(
        None,
        description="Reference to delivery schema (format standards)"
    )

    # Shared assets
    shared_assets: List[str] = Field(
        default_factory=list,
        description="Shared asset IDs (materials, documents, context)"
    )

    # Shared knowledge
    shared_knowledge_refs: List[str] = Field(
        default_factory=list,
        description="Shared knowledge references (data sources, docs)"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional baseline metadata"
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class CapabilityPack(BaseModel):
    """
    Capability Pack - Personal/team capability package.

    Contains lens/agent configuration, playbook, and preset packs
    that can be brought into a workspace for collaboration.
    """
    pack_id: str = Field(..., description="Pack ID, e.g., 'writer.copy-pack@1.0'")
    owner_user_id: str = Field(..., description="Owner user ID")
    name: str = Field(..., description="Pack name")
    description: Optional[str] = Field(None, description="Pack description")

    # Scope definition
    scope: List[str] = Field(
        ...,
        description="Allowed scope: intent codes, card types, step IDs, artifact types"
    )

    # Capability components
    lens_stack: List[str] = Field(
        default_factory=list,
        description="Lens IDs included in this pack"
    )

    playbook_refs: List[str] = Field(
        default_factory=list,
        description="Playbook references included in this pack"
    )

    preset_refs: List[str] = Field(
        default_factory=list,
        description="Preset pack references"
    )

    # Constraints
    side_effect_level: str = Field(
        default="readonly",
        description="Side effect level: readonly (READONLY), soft_write (WRITE_CONTENT), external_write (HIGH_RISK). Aligns with existing SideEffectLevel enum."
    )

    approval_required: bool = Field(
        default=False,
        description="Whether this pack requires approval before use"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional pack metadata"
    )

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

