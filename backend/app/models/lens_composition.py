"""Lens Composition core contract definitions.

Lens Composition represents multi-lens combination recipes.
It is a composition layer on top of Mind Lens instances, not a replacement layer.
"""
from pydantic import BaseModel, Field
from typing import List, Dict, Optional
from enum import Enum
from datetime import datetime


class LensRole(str, Enum):
    """Lens professional role type."""
    DESIGNER = "designer"
    ARTIST = "artist"
    DIRECTOR = "director"
    VOICE_ACTOR = "voice_actor"
    MUSICIAN = "musician"
    WRITER = "writer"
    SCREENWRITER = "screenwriter"
    JOURNALIST = "journalist"
    BRAND = "brand"
    MARKETER = "marketer"


class LensModality(str, Enum):
    """Lens modality type."""
    VISUAL = "visual"
    AUDIO = "audio"
    TEXT = "text"
    BRAND = "brand"


class LensReference(BaseModel):
    """
    Lens reference in composition.

    References existing MindLensInstance, does not redefine Lens.
    """
    lens_instance_id: str = Field(
        ...,
        description="Reference to MindLensInstance.mind_lens_id"
    )
    role: LensRole = Field(..., description="Professional role for composition logic")
    modality: LensModality = Field(..., description="Modality type for grouping")
    weight: float = Field(default=1.0, ge=0.0, le=1.0, description="Weight (0-1)")
    priority: int = Field(default=0, description="Priority (higher number = higher priority)")
    scope: List[str] = Field(default=["all"], description="Application scope")
    locked: bool = Field(default=False, description="Whether locked (cannot be overridden)")


class LensComposition(BaseModel):
    """
    Multi-lens combination recipe.

    This is a composition layer, not a replacement layer. References existing MindLensInstance.
    """
    composition_id: str = Field(..., description="Composition ID")
    workspace_id: str = Field(..., description="Workspace ID")
    name: str = Field(..., description="Composition name")
    description: Optional[str] = Field(None, description="Composition description")
    lens_stack: List[LensReference] = Field(
        ...,
        description="Lens stack (ordered, references MindLensInstance)"
    )
    fusion_strategy: str = Field(
        default="priority_then_weighted",
        description="Fusion strategy: priority | weighted | priority_then_weighted"
    )
    metadata: Optional[Dict] = Field(default=None, description="Additional metadata")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def get_lenses_by_modality(self, modality: LensModality) -> List[LensReference]:
        """Filter lenses by modality."""
        return [lens for lens in self.lens_stack if lens.modality == modality]

    def get_lenses_by_role(self, role: LensRole) -> List[LensReference]:
        """Filter lenses by role."""
        return [lens for lens in self.lens_stack if lens.role == role]

    def get_lenses_by_scope(self, scope: str) -> List[LensReference]:
        """Filter lenses by scope."""
        return [lens for lens in self.lens_stack if scope in lens.scope or "all" in lens.scope]

    def get_total_weight(self) -> float:
        """Calculate total weight."""
        return sum(lens.weight for lens in self.lens_stack)


class FusedLensContext(BaseModel):
    """Fused lens context after fusion."""
    composition_id: str = Field(..., description="Source Composition ID")
    fused_values: Dict = Field(..., description="Fused values")
    source_lenses: List[str] = Field(..., description="Source Lens IDs")
    fusion_log: List[Dict] = Field(default_factory=list, description="Fusion log")
    fusion_strategy: str = Field(..., description="Fusion strategy used")
    applied_at: datetime = Field(default_factory=datetime.utcnow)






