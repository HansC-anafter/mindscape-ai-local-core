"""Reasoning graph routes for execution graph APIs."""

import logging
from typing import List, Optional

from fastapi import HTTPException, Query

from backend.features.workspace.execution_graph_core.models import (
    ReasoningGraphResponse,
)

logger = logging.getLogger(__name__)


async def get_reasoning_graph(trace_id: str) -> ReasoningGraphResponse:
    """
    Get a reasoning graph by trace ID.

    Returns the full reasoning graph structure including nodes, edges, and metadata.
    """
    try:
        from backend.app.services.stores.reasoning_traces_store import ReasoningTracesStore

        store = ReasoningTracesStore()
        trace = store.get_by_id(trace_id)
        if not trace:
            raise HTTPException(
                status_code=404,
                detail=f"Reasoning trace not found: {trace_id}",
            )
        return ReasoningGraphResponse(
            id=trace.id,
            workspace_id=trace.workspace_id,
            execution_id=trace.execution_id,
            assistant_event_id=trace.assistant_event_id,
            graph=trace.graph_json,
            schema_version=trace.schema_version,
            sgr_mode=trace.sgr_mode,
            model=trace.model,
            token_count=trace.token_count,
            latency_ms=trace.latency_ms,
            created_at=trace.created_at.isoformat(),
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Failed to get reasoning graph: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


async def list_reasoning_graphs(
    workspace_id: str = Query(..., description="Workspace ID"),
    execution_id: Optional[str] = Query(None, description="Filter by execution ID"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
) -> List[ReasoningGraphResponse]:
    """
    List reasoning graphs for a workspace.

    Optionally filter by execution_id to find the reasoning graph associated with a
    specific chat execution.
    """
    try:
        from backend.app.services.stores.reasoning_traces_store import ReasoningTracesStore

        store = ReasoningTracesStore()

        if execution_id:
            trace = store.get_by_execution_id_and_workspace(execution_id, workspace_id)
            traces = [trace] if trace else []
        else:
            traces = store.list_by_workspace(workspace_id, limit=limit)

        return [
            ReasoningGraphResponse(
                id=trace.id,
                workspace_id=trace.workspace_id,
                execution_id=trace.execution_id,
                assistant_event_id=trace.assistant_event_id,
                graph=trace.graph_json,
                schema_version=trace.schema_version,
                sgr_mode=trace.sgr_mode,
                model=trace.model,
                token_count=trace.token_count,
                latency_ms=trace.latency_ms,
                created_at=trace.created_at.isoformat(),
            )
            for trace in traces
        ]
    except Exception as exc:
        logger.error(f"Failed to list reasoning graphs: {exc}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))


def register_reasoning_routes(router) -> None:
    """Register reasoning routes on the public execution graph router."""
    router.get("/reasoning/{trace_id}", response_model=ReasoningGraphResponse)(
        get_reasoning_graph
    )
    router.get("/reasoning", response_model=List[ReasoningGraphResponse])(
        list_reasoning_graphs
    )
