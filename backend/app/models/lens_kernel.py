"""
Lens Kernel models for Mind-Lens unified implementation.

These models define the contract between Graph and Workspace layers.
"""
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Literal
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json

from .graph import LensNodeState, GraphNodeType, GraphNodeCategory


def state_to_weight(state: LensNodeState) -> float:
    """State → Weight fixed mapping"""
    return {
        LensNodeState.OFF: 0.0,
        LensNodeState.KEEP: 1.0,
        LensNodeState.EMPHASIZE: 1.4,
    }[state]


class LensNode(BaseModel):
    """Lens Kernel node contract"""
    node_id: str
    node_label: str
    node_type: GraphNodeType
    category: GraphNodeCategory

    state: LensNodeState = Field(default=LensNodeState.KEEP)

    weight: float = Field(default=1.0, description="Derived from state, do not set directly")

    effective_scope: Literal["global", "workspace", "session"] = Field(default="global")
    is_overridden: bool = Field(default=False)
    overridden_from: Optional[Literal["global", "workspace"]] = None

    @validator('weight', always=True)
    def derive_weight(cls, v, values):
        """Weight derived from state"""
        state = values.get('state', LensNodeState.KEEP)
        return state_to_weight(state)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class EffectiveLens(BaseModel):
    """Three-layer stacked effective lens"""
    profile_id: str
    workspace_id: Optional[str]
    session_id: Optional[str]

    nodes: List[LensNode]

    global_preset_id: str
    global_preset_name: str
    workspace_override_count: int = 0
    session_override_count: int = 0

    hash: str = Field(description="Hash of (node_id, state, effective_scope) tuples only")

    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


def compute_lens_hash(nodes: List[LensNode]) -> str:
    """Compute stable hash for lens"""
    stable_tuples = sorted([
        (n.node_id, n.state.value, n.effective_scope)
        for n in nodes
    ])
    content = json.dumps(stable_tuples, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()[:16]


class CompiledLensContext(BaseModel):
    """Compiled lens context for prompt injection"""
    system_prompt_additions: str = Field(default="")
    anti_goals: List[str] = Field(default_factory=list)
    emphasized_values: List[str] = Field(default_factory=list)
    style_rules: List[str] = Field(default_factory=list)
    lens_hash: str

