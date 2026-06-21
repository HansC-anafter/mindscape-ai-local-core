"""Graph read routes for execution graph APIs."""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Query

from backend.app.services.mindscape_graph_service import MindscapeGraphService
from backend.features.workspace.execution_graph_core.dependencies import (
    get_graph_service,
)
from backend.features.workspace.execution_graph_core.models import GraphResponse
from backend.features.workspace.execution_graph_core.serializers import (
    build_graph_response,
)

logger = logging.getLogger(__name__)


async def get_graph(
    workspace_id: Optional[str] = Query(None, description="Workspace ID"),
    workspace_group_id: Optional[str] = Query(None, description="Workspace Group ID"),
    include_reasoning: bool = Query(
        False,
        description="Include reasoning graph nodes (not supported for group queries)",
    ),
    service: MindscapeGraphService = Depends(get_graph_service),
) -> GraphResponse:
    """
    Get mindscape graph for workspace or workspace group.

    Either workspace_id or workspace_group_id must be provided.
    """
    if not workspace_id and not workspace_group_id:
        raise HTTPException(
            status_code=400,
            detail="Either workspace_id or workspace_group_id is required",
        )

    try:
        graph = await service.get_graph(
            workspace_id=workspace_id,
            workspace_group_id=workspace_group_id,
        )

        if include_reasoning:
            if workspace_group_id:
                raise HTTPException(
                    status_code=400,
                    detail="include_reasoning is not supported for group queries",
                )
            try:
                from backend.app.services.stores.reasoning_traces_store import (
                    ReasoningTracesStore,
                )

                traces_store = ReasoningTracesStore()
                traces = traces_store.list_by_workspace(workspace_id, limit=10)
                for trace in traces:
                    try:
                        reasoning_graph = trace.graph
                        service.derive_from_reasoning_graph(
                            workspace_id,
                            reasoning_graph,
                            trace.id,
                        )
                    except Exception as exc:
                        logger.warning(
                            f"Failed to derive reasoning graph {trace.id}: {exc}"
                        )
                graph = await service.get_graph(
                    workspace_id=workspace_id,
                    workspace_group_id=workspace_group_id,
                )
            except Exception as exc:
                logger.warning(f"Failed to include reasoning graphs: {exc}")

        return build_graph_response(graph)
    except Exception as exc:
        logger.error(f"Failed to get graph: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


async def get_group_graph(
    group_id: str,
    service: MindscapeGraphService = Depends(get_graph_service),
) -> GraphResponse:
    """Get aggregated graph for a workspace group."""
    try:
        graph = await service.get_graph(workspace_group_id=group_id)
        return build_graph_response(graph)
    except Exception as exc:
        logger.error(f"Failed to get group graph: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


def register_graph_routes(router) -> None:
    """Register graph read routes on the public execution graph router."""
    router.get("/graph", response_model=GraphResponse)(get_graph)
    router.get("/groups/{group_id}/graph", response_model=GraphResponse)(
        get_group_graph
    )
