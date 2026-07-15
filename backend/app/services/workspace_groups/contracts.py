"""Typed contracts for normalized Workspace Group topology."""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, model_validator


WorkspaceGroupRole = Literal["dispatch", "cell"]


class WorkspaceGroupMember(BaseModel):
    workspace_id: str
    role: WorkspaceGroupRole
    title: Optional[str] = None
    visibility: Optional[str] = None
    joined_at: Optional[datetime] = None


class WorkspaceGroupTopology(BaseModel):
    id: str
    display_name: str
    owner_user_id: str
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    revision: int = 1
    members: List[WorkspaceGroupMember] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def role_map(self) -> Dict[str, str]:
        return {member.workspace_id: member.role for member in self.members}

    @property
    def dispatch_workspace_id(self) -> Optional[str]:
        return next(
            (
                member.workspace_id
                for member in self.members
                if member.role == "dispatch"
            ),
            None,
        )

    @property
    def cell_workspace_ids(self) -> List[str]:
        return [
            member.workspace_id for member in self.members if member.role == "cell"
        ]

    @property
    def is_ready(self) -> bool:
        return self.dispatch_workspace_id is not None and bool(self.cell_workspace_ids)


class WorkspaceGroupMemberInput(BaseModel):
    workspace_id: str = Field(min_length=1, max_length=64)
    role: WorkspaceGroupRole = "cell"


class WorkspaceGroupCreate(BaseModel):
    id: Optional[str] = Field(default=None, min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    members: List[WorkspaceGroupMemberInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_members(self):
        _validate_member_set(self.members)
        return self


class WorkspaceGroupUpdate(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    members: Optional[List[WorkspaceGroupMemberInput]] = None

    @model_validator(mode="after")
    def validate_members(self):
        if self.members is not None:
            _validate_member_set(self.members)
        return self


class ActiveWorkspaceGroupContext(BaseModel):
    group_id: str
    workspace_id: str
    role: WorkspaceGroupRole
    revision: int
    topology: WorkspaceGroupTopology


class WorkspaceGroupTopologySnapshot(BaseModel):
    id: str
    group_id: str
    display_name: str
    group_revision: int
    content_hash: str
    members: List[WorkspaceGroupMember] = Field(default_factory=list)
    dispatch_workspace_id: Optional[str] = None
    cell_workspace_ids: List[str] = Field(default_factory=list)
    created_by_user_id: str
    created_at: Optional[datetime] = None

    @property
    def role_map(self) -> Dict[str, str]:
        return {member.workspace_id: member.role for member in self.members}


def _validate_member_set(members: List[WorkspaceGroupMemberInput]) -> None:
    workspace_ids = [member.workspace_id for member in members]
    if len(workspace_ids) != len(set(workspace_ids)):
        raise ValueError("duplicate workspace membership")
    if sum(member.role == "dispatch" for member in members) > 1:
        raise ValueError("a workspace group can have at most one dispatch workspace")
