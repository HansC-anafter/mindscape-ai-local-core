"""
Lens Preset Package models for Mind-Lens unified implementation.

Preset Package enables distribution and subscription of lens presets.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone

from .graph import GraphNode, GraphEdge, LensProfileNode


class LensPresetPackage(BaseModel):
    """Distributable preset package"""
    id: str
    name: str
    description: str
    version: str = Field(..., description="Semver version")
    author: str
    license: str = Field(default="MIT", description="MIT / proprietary / subscription")

    nodes: List[GraphNode] = Field(default_factory=list)
    profile_nodes: List[LensProfileNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)

    signature: Optional[str] = None
    checksum: str

    tags: List[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

