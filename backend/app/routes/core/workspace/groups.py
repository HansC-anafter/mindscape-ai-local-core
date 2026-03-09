"""Workspace Groups API — topology and membership queries."""

import logging
from typing import List, Dict, Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.stores.postgres.workspace_group_store import (
    PostgresWorkspaceGroupStore,
)
from app.services.stores.postgres.group_membership_store import GroupMembershipStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/workspace-groups", tags=["workspace-groups"])


# ── Response schemas ──


class WorkspaceGroupMember(BaseModel):
    """A workspace within a group."""

    workspace_id: str
    role: str
    title: Optional[str] = None
    visibility: Optional[str] = None
    joined_at: Optional[str] = None


class WorkspaceGroupResponse(BaseModel):
    """Full group details including member list."""

    id: str
    display_name: str
    owner_user_id: str
    description: Optional[str] = None
    role_map: Dict[str, str] = {}
    members: List[WorkspaceGroupMember] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class WorkspaceGroupMembersResponse(BaseModel):
    """Member list for a group."""

    group_id: str
    members: List[WorkspaceGroupMember] = []
    total: int = 0


# ── Endpoints ──


class WorkspaceGroupListResponse(BaseModel):
    """Paginated list of workspace groups."""

    groups: List[WorkspaceGroupResponse] = []
    total: int = 0


@router.get("", response_model=WorkspaceGroupListResponse)
async def list_workspace_groups():
    """List all workspace groups."""
    from sqlalchemy import text as sa_text

    group_store = PostgresWorkspaceGroupStore()
    membership_store = GroupMembershipStore()

    with group_store.get_connection() as conn:
        rows = conn.execute(
            sa_text("SELECT * FROM workspace_groups ORDER BY updated_at DESC LIMIT 200")
        ).fetchall()

    result = []
    for row in rows:
        group = group_store._row_to_group(row)
        members_raw = membership_store.list_workspaces_in_group(group.id)
        members = [
            WorkspaceGroupMember(
                workspace_id=m["workspace_id"],
                role=m["role"],
                title=m.get("title"),
                visibility=m.get("visibility"),
                joined_at=m.get("joined_at"),
            )
            for m in members_raw
        ]
        result.append(
            WorkspaceGroupResponse(
                id=group.id,
                display_name=group.display_name,
                owner_user_id=group.owner_user_id,
                description=group.description,
                role_map=group.role_map,
                members=members,
                created_at=group.created_at.isoformat() if group.created_at else None,
                updated_at=group.updated_at.isoformat() if group.updated_at else None,
            )
        )

    return WorkspaceGroupListResponse(groups=result, total=len(result))


@router.get("/{group_id}", response_model=WorkspaceGroupResponse)
async def get_workspace_group(group_id: str):
    """Get workspace group details including member list."""
    group_store = PostgresWorkspaceGroupStore()
    membership_store = GroupMembershipStore()

    group = group_store.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

    # Fetch members via membership table (includes workspace title and visibility)
    members_raw = membership_store.list_workspaces_in_group(group_id)
    members = [
        WorkspaceGroupMember(
            workspace_id=m["workspace_id"],
            role=m["role"],
            title=m.get("title"),
            visibility=m.get("visibility"),
            joined_at=m.get("joined_at"),
        )
        for m in members_raw
    ]

    return WorkspaceGroupResponse(
        id=group.id,
        display_name=group.display_name,
        owner_user_id=group.owner_user_id,
        description=group.description,
        role_map=group.role_map,
        members=members,
        created_at=group.created_at.isoformat() if group.created_at else None,
        updated_at=group.updated_at.isoformat() if group.updated_at else None,
    )


@router.get("/{group_id}/members", response_model=WorkspaceGroupMembersResponse)
async def list_group_members(group_id: str):
    """List all workspaces in a group."""
    group_store = PostgresWorkspaceGroupStore()
    membership_store = GroupMembershipStore()

    # Verify group exists
    group = group_store.get(group_id)
    if not group:
        raise HTTPException(status_code=404, detail=f"Group {group_id} not found")

    members_raw = membership_store.list_workspaces_in_group(group_id)
    members = [
        WorkspaceGroupMember(
            workspace_id=m["workspace_id"],
            role=m["role"],
            title=m.get("title"),
            visibility=m.get("visibility"),
            joined_at=m.get("joined_at"),
        )
        for m in members_raw
    ]

    return WorkspaceGroupMembersResponse(
        group_id=group_id,
        members=members,
        total=len(members),
    )
