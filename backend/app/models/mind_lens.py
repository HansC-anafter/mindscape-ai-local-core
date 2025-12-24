"""Mind Lens core contract definitions.

Mind Lens represents perspective/viewpoint (how to see, where to focus attention, how to make trade-offs).
It is distinct from Policy (constraints) - Lens is like driving style, Policy is like guardrails.

Key characteristics:
- Lens is execution context, not part of task
- Lens can be stacked, weighted, scoped
- Lens is replaceable and versionable
- Lens focuses on "how to interpret" not "what cannot be done"
"""
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime


class Dimension(BaseModel):
    """A dimension in Mind Lens schema defining perspective aspects."""
    key: str
    label: str
    type: str
    options: Optional[List[str]] = None
    description: Optional[str] = None
    from_modalities: List[str] = []
    encoding: Optional[Dict[str, Any]] = None


class MindLensSchema(BaseModel):
    """Professional-level schema defining dimensions for a role perspective."""
    schema_id: str
    role: str
    label: Optional[str] = None
    dimensions: List[Dimension]
    version: str = "0.1"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class MindLensInstance(BaseModel):
    """Personal/author-level instance of a Mind Lens (perspective/viewpoint)."""
    mind_lens_id: str
    schema_id: str
    owner_user_id: str
    role: str
    label: Optional[str] = None
    description: Optional[str] = None
    values: Dict[str, Any]
    source: Optional[Dict[str, Any]] = None
    version: str = "0.1"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class RuntimeMindLens(BaseModel):
    """Resolved Mind Lens for runtime execution context."""
    resolved_mind_lens_id: str
    role: str
    source_lenses: List[str]
    values: Dict[str, Any]
    bound_brains: Optional[List[str]] = None
    weights: Optional[Dict[str, float]] = None
    created_at: Optional[datetime] = None


class LensSpec(BaseModel):
    """
    Executable Lens specification.

    Lens is not just a label, but a compilable execution context.
    It can inject prompts, style rules, and transformers into steps.
    """
    lens_id: str = Field(..., description="Lens ID, e.g., 'writer.hemingway'")
    version: str = Field(..., description="Version, e.g., '1.0.0'")
    category: str = Field(..., description="Category: writer, designer, director, etc.")
    applies_to: List[str] = Field(
        ...,
        description="Modalities this lens applies to: text, image, audio, etc."
    )

    inject: Dict[str, Any] = Field(
        ...,
        description="Injection rules for compilation. Structure: {system, style_rules, prompt_prefix, prompt_suffix}"
    )

    params_schema: Dict[str, Any] = Field(
        default_factory=dict,
        description="Parameter schema for lens customization"
    )

    transformers: Optional[List[str]] = Field(
        None,
        description="Optional transformer function names (advanced)"
    )

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

