"""Workspace-scoped composition graph API."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Path as PathParam, Query

from backend.app.models.object_runtime import (
    CompositionGraphCompileRequest,
    CompositionGraphCompileResponse,
    CompositionGraphContractsResponse,
    CompositionGraphDraftCreateRequest,
    CompositionGraphDraftListResponse,
    CompositionGraphDraftResponse,
    CompositionGraphDraftUpdateRequest,
    CompositionGraphImportExportPayload,
    CompositionGraphImportRequest,
    CompositionGraphImportResponse,
)
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_store, get_workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.object_runtime.composition_graph_service import (
    CompositionGraphService,
)
from backend.app.services.stores.installed_packs_store import InstalledPacksStore

router = APIRouter()


def _resolve_local_core_root() -> Path:
    return Path(__file__).resolve().parents[5]


def _get_installed_pack_ids() -> list[str]:
    return InstalledPacksStore().list_installed_pack_ids()


def _build_service(store: MindscapeStore) -> CompositionGraphService:
    return CompositionGraphService(
        artifacts_store=store.artifacts,
        local_core_root=_resolve_local_core_root(),
        installed_pack_ids=_get_installed_pack_ids(),
    )


@router.get(
    "/{workspace_id}/composition-graph/contracts",
    response_model=CompositionGraphContractsResponse,
)
async def get_composition_graph_contracts(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphContractsResponse:
    del workspace
    return _build_service(store).list_contracts(workspace_id)


@router.get(
    "/{workspace_id}/composition-graph/drafts",
    response_model=CompositionGraphDraftListResponse,
)
async def list_composition_graph_drafts(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    thread_id: Optional[str] = Query(None, description="Thread ID"),
    limit: int = Query(100, ge=1, le=500),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphDraftListResponse:
    del workspace
    return _build_service(store).list_drafts(
        workspace_id,
        thread_id=thread_id,
        limit=limit,
    )


@router.post(
    "/{workspace_id}/composition-graph/drafts",
    response_model=CompositionGraphDraftResponse,
)
async def create_composition_graph_draft(
    request: CompositionGraphDraftCreateRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphDraftResponse:
    del workspace
    return _build_service(store).create_draft(workspace_id, request)


@router.put(
    "/{workspace_id}/composition-graph/drafts/{draft_id}",
    response_model=CompositionGraphDraftResponse,
)
async def update_composition_graph_draft(
    request: CompositionGraphDraftUpdateRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    draft_id: str = PathParam(..., description="Draft ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphDraftResponse:
    del workspace
    return _build_service(store).update_draft(workspace_id, draft_id, request)


@router.get(
    "/{workspace_id}/composition-graph/drafts/{draft_id}/export",
    response_model=CompositionGraphImportExportPayload,
)
async def export_composition_graph_draft(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    draft_id: str = PathParam(..., description="Draft ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphImportExportPayload:
    del workspace
    return _build_service(store).export_draft(workspace_id, draft_id)


@router.post(
    "/{workspace_id}/composition-graph/import",
    response_model=CompositionGraphImportResponse,
)
async def import_composition_graph(
    request: CompositionGraphImportRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphImportResponse:
    del workspace
    return _build_service(store).import_graph(workspace_id, request)


@router.post(
    "/{workspace_id}/composition-graph/compile",
    response_model=CompositionGraphCompileResponse,
)
async def compile_composition_graph(
    request: CompositionGraphCompileRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphCompileResponse:
    del workspace
    return await _build_service(store).compile_graph(workspace_id, request)
