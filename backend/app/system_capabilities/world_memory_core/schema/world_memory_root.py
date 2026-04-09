from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from .world_state_snapshot import WorldStateSnapshot


class WorldMemoryRoot(BaseModel):
    workspace_id: str = Field(..., description="Workspace identifier")
    current_snapshot: WorldStateSnapshot = Field(..., description="Current normalized world-state snapshot")
    history_snapshot_ids: List[str] = Field(default_factory=list)
    source_receipt_types: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    active_geo_anchor: Optional[Dict[str, Any]] = Field(None)
