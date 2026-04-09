from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class WorldMemoryDelta(BaseModel):
    workspace_id: str = Field(..., description="Workspace identifier")
    snapshot_id: str = Field(..., description="Snapshot identifier")
    changed_fields: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
