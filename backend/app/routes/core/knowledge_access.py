"""Thin HTTP facade for workspace-scoped knowledge access governance."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.dependencies.auth import (
    AuthContext,
    build_retrieval_access_context,
    get_current_user,
)
from backend.app.services.knowledge_authorization.access_context_factory import (
    RetrievalScopeDenied,
)
from backend.app.services.knowledge_authorization.governance import (
    KnowledgeAccessForbiddenError,
    KnowledgeAccessNotFoundError,
    KnowledgeAccessReplacementCommand,
    KnowledgeAccessService,
    KnowledgeProjectionActionCommand,
)
from backend.app.services.knowledge_authorization.store import (
    KnowledgeAuthorizationConflictError,
)


router = APIRouter(
    prefix="/api/v1/workspaces/{workspace_id}/knowledge-access",
    tags=["knowledge-access"],
)
service = KnowledgeAccessService()


def _translate_error(exc: Exception) -> HTTPException:
    if isinstance(
        exc,
        (KnowledgeAccessForbiddenError, RetrievalScopeDenied),
    ):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, KnowledgeAccessNotFoundError):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, KnowledgeAuthorizationConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(
        status_code=500,
        detail="knowledge_access_operation_failed",
    )


async def _context(auth: AuthContext, workspace_id: str):
    return await asyncio.to_thread(
        build_retrieval_access_context,
        auth,
        requested_workspace_ids=(workspace_id,),
    )


@router.get("")
async def list_knowledge_access(
    workspace_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=1024),
    auth: AuthContext = Depends(get_current_user),
):
    try:
        context = await _context(auth, workspace_id)
        return await asyncio.to_thread(
            service.list_summary,
            context=context,
            workspace_id=workspace_id,
            limit=limit,
            cursor=cursor,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.get("/{resource_id}")
async def get_knowledge_access(
    workspace_id: str,
    resource_id: str,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        context = await _context(auth, workspace_id)
        return await asyncio.to_thread(
            service.get_detail,
            context=context,
            workspace_id=workspace_id,
            resource_id=resource_id,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.put("/{resource_id}")
async def replace_knowledge_access(
    workspace_id: str,
    resource_id: str,
    command: KnowledgeAccessReplacementCommand,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        context = await _context(auth, workspace_id)
        return await asyncio.to_thread(
            service.replace_grants,
            context=context,
            workspace_id=workspace_id,
            resource_id=resource_id,
            command=command,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


@router.post("/{resource_id}/actions")
async def run_knowledge_projection_action(
    workspace_id: str,
    resource_id: str,
    command: KnowledgeProjectionActionCommand,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        context = await _context(auth, workspace_id)
        return await asyncio.to_thread(
            service.run_projection_action,
            context=context,
            workspace_id=workspace_id,
            resource_id=resource_id,
            command=command,
        )
    except Exception as exc:
        raise _translate_error(exc) from exc


__all__ = ["router"]
