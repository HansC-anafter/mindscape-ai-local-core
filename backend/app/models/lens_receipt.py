"""
Lens Receipt models for Mind-Lens observability.

Lens Receipt records how the lens affected the execution output.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

from .graph import LensNodeState


class TriggeredNode(BaseModel):
    """Node that was triggered during execution"""
    node_id: str
    node_label: str
    state: LensNodeState
    effective_scope: str
    contribution: Optional[str] = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class LensReceipt(BaseModel):
    """Rendering receipt"""
    id: str
    execution_id: str
    workspace_id: str
    effective_lens_hash: str
    triggered_nodes: List[TriggeredNode] = Field(default_factory=list)
    base_output: Optional[str] = None
    lens_output: Optional[str] = None
    diff_summary: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

