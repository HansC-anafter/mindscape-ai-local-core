"""Authorized HTTP seam over Workspace Group and Knowledge Projection facades."""

from __future__ import annotations

import asyncio
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from backend.app.dependencies.auth import AuthContext, get_current_user
from backend.app.services.knowledge_projection.contracts import (
    GroupSynthesisHandoff,
    GroupSynthesisReviewCommand,
)
from backend.app.services.knowledge_projection.facade import KnowledgeProjectionFacade
from backend.app.services.knowledge_projection.group_context import GroupKnowledgeAccessError
from backend.app.services.knowledge_projection.synthesis import GroupSynthesisStateError
from backend.app.services.knowledge_projection.synthesis_repository import GroupSynthesisBoundaryError
from backend.app.services.workspace_groups.facade import WorkspaceGroupFacade
from backend.app.services.workspace_groups.snapshot_service import WorkspaceGroupSnapshotService
from backend.app.services.workspace_groups.topology_service import (
    WorkspaceGroupAccessError,
    WorkspaceGroupNotFoundError,
)


router = APIRouter(prefix="/api/v1/knowledge-foundation", tags=["knowledge-foundation"])
group_facade = WorkspaceGroupFacade()
snapshot_service = WorkspaceGroupSnapshotService()
knowledge_facade = KnowledgeProjectionFacade()


class ScopeAdmissionCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1, max_length=64)
    mode: Literal["personal", "organization"]
    group_id: Optional[str] = Field(default=None, max_length=64)
    topology_snapshot_id: Optional[str] = Field(default=None, max_length=64)


class ReviewCommandBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "request_changes", "reject"]
    actor_user_id: Optional[str] = None
    reason: str = Field(default="", max_length=4000)


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(exc, WorkspaceGroupNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, (WorkspaceGroupAccessError, GroupKnowledgeAccessError)):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (GroupSynthesisBoundaryError, GroupSynthesisStateError, ValueError)):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(status_code=500, detail="knowledge foundation operation failed")


def _require_workspace(auth: AuthContext, workspace_id: str) -> None:
    if workspace_id not in set(auth.workspace_ids):
        raise WorkspaceGroupAccessError("workspace is outside the authenticated scope")


@router.post("/scopes/admit")
async def admit_scope(
    command: ScopeAdmissionCommand,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        _require_workspace(auth, command.workspace_id)
        if command.mode == "personal":
            if command.group_id is not None or command.topology_snapshot_id is not None:
                raise ValueError("personal scope cannot carry group topology")
            return {
                "mode": "personal",
                "workspace_id": command.workspace_id,
                "actor_user_id": auth.user_id,
            }
        if not command.group_id:
            raise ValueError("organization scope requires an explicit group id")
        context = await asyncio.to_thread(
            group_facade.resolve_context,
            active_group_id=command.group_id,
            workspace_id=command.workspace_id,
            actor_user_id=auth.user_id,
            allowed_group_ids=auth.group_ids,
        )
        if context is None:
            raise ValueError("organization scope resolution failed")
        if command.topology_snapshot_id:
            snapshot = await asyncio.to_thread(snapshot_service.get, command.topology_snapshot_id)
            if snapshot is None:
                raise ValueError("workspace group snapshot not found")
            if snapshot.group_id != context.group_id or snapshot.group_revision != context.revision:
                raise ValueError("workspace group snapshot is stale")
            if command.workspace_id not in snapshot.role_map:
                raise WorkspaceGroupAccessError("workspace is outside the admitted snapshot")
        else:
            snapshot = await asyncio.to_thread(
                snapshot_service.get_or_create,
                context,
                actor_user_id=auth.user_id,
            )
        return {
            "mode": "organization",
            "workspace_id": command.workspace_id,
            "actor_user_id": auth.user_id,
            "topology_snapshot": snapshot.model_dump(mode="json"),
        }
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/group-packet")
async def compile_group_packet(
    topology_snapshot_id: str,
    requesting_workspace_id: str,
    agent_role: Optional[str] = None,
    preview: bool = False,
    limit: int = Query(default=50, ge=1, le=200),
    auth: AuthContext = Depends(get_current_user),
):
    try:
        _require_workspace(auth, requesting_workspace_id)
        packet = await asyncio.to_thread(
            knowledge_facade.compile_group_packet,
            topology_snapshot_id=topology_snapshot_id,
            requesting_workspace_id=requesting_workspace_id,
            actor_user_id=auth.user_id,
            agent_role=agent_role,
            preview=preview,
            allowed_group_ids=auth.group_ids,
            limit=limit,
        )
        return packet.model_dump(mode="json")
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/group-synthesis")
async def commit_group_synthesis(
    handoff: GroupSynthesisHandoff,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        await asyncio.to_thread(
            group_facade.get_group,
            handoff.group_id,
            actor_user_id=auth.user_id,
            allowed_group_ids=auth.group_ids,
        )
        receipt = await asyncio.to_thread(knowledge_facade.commit_group_synthesis, handoff)
        return receipt.model_dump(mode="json")
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/group-synthesis/{receipt_id}/review")
async def review_group_synthesis(
    receipt_id: str,
    body: ReviewCommandBody,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        if body.actor_user_id is not None and body.actor_user_id != auth.user_id:
            raise WorkspaceGroupAccessError("review actor differs from authenticated user")
        command = GroupSynthesisReviewCommand(
            synthesis_receipt_id=receipt_id,
            decision=body.decision,
            actor_user_id=auth.user_id,
            reason=body.reason,
        )
        receipt = await asyncio.to_thread(
            knowledge_facade.review_group_synthesis,
            command,
            allowed_group_ids=auth.group_ids,
        )
        return receipt.model_dump(mode="json")
    except Exception as exc:
        raise _translate_error(exc) from exc
