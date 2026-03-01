"""
WorkspaceGroup model — groups of workspaces for cross-workspace dispatch.

A WorkspaceGroup defines an organizational unit where one workspace acts as a
dispatch coordinator (role='dispatch') and others act as execution cells
(role='cell'). The dispatch workspace's Meeting Engine can route tasks to
cell workspaces based on data asset ownership.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class WorkspaceGroup(BaseModel):
    """A logical group of workspaces that share a dispatch boundary."""

    id: str = Field(..., description="Unique group identifier")
    display_name: str = Field(..., description="Human-readable group name")
    owner_user_id: str = Field(..., description="Owner user ID")

    # Role map: workspace_id -> role (dispatch | cell)
    role_map: Dict[str, str] = Field(
        default_factory=dict,
        description="Workspace role assignments: {workspace_id: 'dispatch' | 'cell'}",
    )

    description: Optional[str] = Field(None, description="Group description")
    metadata: Optional[Dict] = Field(
        default_factory=dict, description="Extensible metadata"
    )

    created_at: datetime = Field(
        default_factory=_utc_now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=_utc_now, description="Last update timestamp"
    )

    model_config = {
        "from_attributes": True,
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }

    # ── Derived helpers ──

    @property
    def workspace_ids(self) -> List[str]:
        """All workspace IDs in this group."""
        return list(self.role_map.keys())

    @property
    def dispatch_workspace_id(self) -> Optional[str]:
        """The workspace acting as dispatch coordinator, if any."""
        for ws_id, role in self.role_map.items():
            if role == "dispatch":
                return ws_id
        return None

    @property
    def cell_workspace_ids(self) -> List[str]:
        """Workspace IDs acting as execution cells."""
        return [ws_id for ws_id, role in self.role_map.items() if role == "cell"]
