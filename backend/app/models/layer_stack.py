"""Layer Stack models for executable layer configuration."""
from typing import List, Dict, Optional, Any
from pydantic import BaseModel, Field
from datetime import datetime
from enum import Enum


class LayerItem(BaseModel):
    """Single layer in stack."""
    lens_id: str = Field(
        ...,
        description="Lens ID with version, e.g., 'writer.hemingway@1.0.0'"
    )
    enabled: bool = Field(default=True, description="Whether layer is enabled")
    scope: List[str] = Field(
        default=["all"],
        description="Affected steps/artifact types, e.g., ['GeneratePosts', 'text']"
    )
    params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Layer parameters"
    )
    priority: int = Field(
        default=0,
        description="Priority (higher number = higher priority)"
    )
    weight: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Weight for weighted fusion (0-1)"
    )


class LayerStack(BaseModel):
    """
    Executable layer stack configuration.

    This is a compilable configuration that can be applied to execution steps.
    Each layer can be enabled/disabled, scoped to specific steps, and parameterized.
    """
    stack_id: str = Field(..., description="Unique stack ID")
    execution_id: str = Field(..., description="Associated execution ID")
    layers: List[LayerItem] = Field(..., description="Ordered list of layers")
    compiled_context: Optional[Dict[str, Any]] = Field(
        None,
        description="Compiled context (cached after compilation)"
    )
    context_hash: Optional[str] = Field(
        None,
        description="Hash of compiled context for dependency tracking"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class ArtifactProvenance(BaseModel):
    """
    Artifact provenance tracking.

    Tracks which layers were used to generate an artifact,
    allowing impact analysis when layers change.
    """
    execution_id: str = Field(..., description="Execution ID")
    step_id: str = Field(..., description="Step ID that generated artifact")
    context_hash: str = Field(
        ...,
        description="Hash of compiled context used (for dependency tracking)"
    )
    layers_used: List[str] = Field(
        ...,
        description="Lens IDs used in generation"
    )
    layer_stack_id: Optional[str] = Field(
        None,
        description="Layer stack ID used"
    )
    compiled_context_snapshot: Optional[Dict[str, Any]] = Field(
        None,
        description="Snapshot of compiled context (for debugging/replay)"
    )
    pack_id: Optional[str] = Field(
        None,
        description="Capability pack ID used (for BYOP/BYOL tracking)"
    )
    playbook_version: Optional[str] = Field(
        None,
        description="Playbook version used"
    )
    card_id: Optional[str] = Field(
        None,
        description="Card/execution card ID (for scope tracking)"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ImpactAnalysis(BaseModel):
    """Impact analysis result when layers change."""
    affected_artifacts: List[str] = Field(
        ...,
        description="Artifact IDs affected by layer changes"
    )
    affected_steps: List[str] = Field(
        ...,
        description="Step IDs affected by layer changes"
    )
    suggested_actions: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Suggested regeneration actions"
    )


class RegenerationAction(BaseModel):
    """Suggested regeneration action."""
    action_type: str = Field(
        ...,
        description="Type: 'rerun_step', 'rewrite_artifact', 'branch_execution'"
    )
    target_id: str = Field(..., description="Step ID or artifact ID")
    description: str = Field(..., description="Human-readable description")
    estimated_cost: Optional[str] = Field(None, description="Estimated cost/time")

