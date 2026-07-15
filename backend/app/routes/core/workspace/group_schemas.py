"""HTTP projections for the Workspace Group facade."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from backend.app.services.workspace_groups.contracts import WorkspaceGroupTopology


class WorkspaceGroupMemberResponse(BaseModel):
    workspace_id: str
    role: str
    title: Optional[str] = None
    visibility: Optional[str] = None
    joined_at: Optional[datetime] = None


class WorkspaceGroupResponse(BaseModel):
    id: str
    display_name: str
    owner_user_id: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    revision: int
    role_map: Dict[str, str] = Field(default_factory=dict)
    members: List[WorkspaceGroupMemberResponse] = Field(default_factory=list)
    dispatch_workspace_id: Optional[str] = None
    cell_workspace_ids: List[str] = Field(default_factory=list)
    is_ready: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @classmethod
    def from_topology(cls, topology: WorkspaceGroupTopology):
        return cls(
            **topology.model_dump(),
            role_map=topology.role_map,
            dispatch_workspace_id=topology.dispatch_workspace_id,
            cell_workspace_ids=topology.cell_workspace_ids,
            is_ready=topology.is_ready,
        )


class WorkspaceGroupListResponse(BaseModel):
    groups: List[WorkspaceGroupResponse] = Field(default_factory=list)
    total: int = 0


class WorkspaceGroupMembersResponse(BaseModel):
    group_id: str
    members: List[WorkspaceGroupMemberResponse] = Field(default_factory=list)
    total: int = 0
