"""Thin HTTP seam for explicit knowledge benchmark operations."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.app.dependencies.auth import (
    AuthContext,
    build_retrieval_access_context,
    get_current_user,
)
from backend.app.services.knowledge_benchmark import KnowledgeBenchmarkFacade
from backend.app.services.knowledge_benchmark.contracts import (
    BenchmarkCatalogCommand,
    BenchmarkExecutionCommand,
)
from backend.app.services.workspace_groups.facade import WorkspaceGroupFacade
from backend.app.services.workspace_groups.topology_service import (
    WorkspaceGroupAccessError,
    WorkspaceGroupNotFoundError,
)


router = APIRouter(
    prefix="/api/v1/knowledge-foundation/benchmarks",
    tags=["knowledge-benchmarks"],
)
benchmark_facade = KnowledgeBenchmarkFacade()
group_facade = WorkspaceGroupFacade()


async def _admit(
    *,
    auth: AuthContext,
    workspace_id: str,
    group_id: str,
    require_dispatch: bool,
):
    topology = await asyncio.to_thread(
        group_facade.get_group,
        group_id,
        actor_user_id=auth.user_id,
        allowed_group_ids=auth.group_ids,
    )
    if workspace_id not in topology.role_map:
        raise WorkspaceGroupAccessError(
            "benchmark workspace is outside the group"
        )
    if require_dispatch and topology.dispatch_workspace_id != workspace_id:
        raise WorkspaceGroupAccessError(
            "benchmark catalog must be owned by the group dispatch"
        )
    return await asyncio.to_thread(
        build_retrieval_access_context,
        auth,
        requested_workspace_ids=(workspace_id,),
        requested_group_ids=(group_id,),
    )


def _translate(exc: Exception) -> HTTPException:
    if isinstance(exc, (PermissionError, WorkspaceGroupAccessError)):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, (LookupError, WorkspaceGroupNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=409, detail=str(exc))
    return HTTPException(
        status_code=500,
        detail="knowledge_benchmark_operation_failed",
    )


@router.post("/catalogs")
async def register_catalog(
    command: BenchmarkCatalogCommand,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        context = await _admit(
            auth=auth,
            workspace_id=command.workspace_id,
            group_id=command.group_id,
            require_dispatch=True,
        )
        return await benchmark_facade.register_catalog(
            command,
            access_context=context,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate(exc) from exc


@router.post("/execute")
async def execute_question(
    command: BenchmarkExecutionCommand,
    auth: AuthContext = Depends(get_current_user),
):
    try:
        context = await _admit(
            auth=auth,
            workspace_id=command.workspace_id,
            group_id=command.group_id,
            require_dispatch=False,
        )
        return await benchmark_facade.execute(
            command,
            access_context=context,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate(exc) from exc


@router.get("/stats")
async def benchmark_stats(
    workspace_id: str,
    group_id: str,
    catalog_id: str,
    catalog_revision: str,
    limit: int = Query(default=200, ge=1, le=500),
    auth: AuthContext = Depends(get_current_user),
):
    try:
        context = await _admit(
            auth=auth,
            workspace_id=workspace_id,
            group_id=group_id,
            require_dispatch=False,
        )
        return await benchmark_facade.stats(
            access_context=context,
            group_id=group_id,
            catalog_id=catalog_id,
            catalog_revision=catalog_revision,
            limit=limit,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise _translate(exc) from exc


__all__ = ["router"]
