from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class WorldCardProjection(BaseModel):
    title: str = Field("World Card", description="Projection title")
    summary_lines: List[str] = Field(default_factory=list)
    constraints: List[str] = Field(default_factory=list)
    suggested_focus: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
