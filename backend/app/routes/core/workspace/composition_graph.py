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
    CompositionGraphNodeOptionsResponse,
    CompositionGraphRunRequest,
    CompositionGraphRunResponse,
    CompositionGraphRunResumeRequest,
)
from backend.app.models.run_harness import RunHarnessObservation
from backend.app.models.workspace import Workspace
from backend.app.routes.workspace_dependencies import get_store, get_workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.object_runtime.composition_graph_service import (
    CompositionGraphService,
)
from backend.app.services.run_harness.composition_graph_adapter import (
    CompositionGraphHarnessAdapter,
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
    compiled = await _build_service(store).compile_graph(workspace_id, request)
    if request.output_mode == "run_harness_spec":
        return CompositionGraphHarnessAdapter().compile_spec(
            workspace_id=workspace_id,
            request=request,
            compiled=compiled,
        )
    return compiled


@router.post(
    "/{workspace_id}/composition-graph/run",
    response_model=CompositionGraphRunResponse,
)
async def run_composition_graph(
    request: CompositionGraphRunRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphRunResponse:
    del workspace
    return await _build_service(store).start_run(workspace_id, request)


@router.get(
    "/{workspace_id}/composition-graph/runs/{graph_run_id}",
    response_model=CompositionGraphRunResponse,
)
async def get_composition_graph_run(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    graph_run_id: str = PathParam(..., description="Composition graph run ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphRunResponse:
    del workspace
    return _build_service(store).get_run(workspace_id, graph_run_id)


@router.get(
    "/{workspace_id}/composition-graph/runs/{graph_run_id}/run-harness-observation",
    response_model=RunHarnessObservation,
)
async def get_composition_graph_run_harness_observation(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    graph_run_id: str = PathParam(..., description="Composition graph run ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> RunHarnessObservation:
    del workspace
    response = _build_service(store).get_run(workspace_id, graph_run_id)
    return CompositionGraphHarnessAdapter().map_observation(
        workspace_id=workspace_id,
        run=response.run,
    )


@router.post(
    "/{workspace_id}/composition-graph/runs/{graph_run_id}/resume",
    response_model=CompositionGraphRunResponse,
)
async def resume_composition_graph_run(
    request: CompositionGraphRunResumeRequest,
    workspace_id: str = PathParam(..., description="Workspace ID"),
    graph_run_id: str = PathParam(..., description="Composition graph run ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphRunResponse:
    del workspace
    return await _build_service(store).resume_run(workspace_id, graph_run_id, request)


@router.get(
    "/{workspace_id}/composition-graph/node-options",
    response_model=CompositionGraphNodeOptionsResponse,
)
async def get_composition_graph_node_options(
    workspace_id: str = PathParam(..., description="Workspace ID"),
    node_type: str = Query(..., min_length=1),
    field: str = Query(..., min_length=1),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> CompositionGraphNodeOptionsResponse:
    del workspace
    return await _build_service(store).resolve_node_options(
        workspace_id,
        node_type=node_type,
        field=field,
    )
