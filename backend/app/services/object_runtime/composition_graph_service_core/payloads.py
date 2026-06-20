"""Payload builders and result normalizers for composition graph service."""

from __future__ import annotations

import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

from backend.app.models.object_runtime import (
    CompositionGraphCommandEnvelopeDraft,
    CompositionGraphCompileRequest,
    CompositionGraphCompileResponse,
    CompositionGraphDiagnostic,
    CompositionGraphDraftResponse,
    CompositionGraphEdge,
    CompositionGraphNode,
    CompositionGraphNodeOption,
    CompositionGraphNodeOptionsResponse,
    CompositionGraphRun,
    CompositionGraphRunNodeState,
    CompositionGraphRunRequest,
)
from backend.app.services.object_runtime.composition_graph_run_store import utc_iso
from backend.app.services.object_runtime.composition_graph_service_core.constants import (
    COMPOSITION_GRAPH_SCHEMA_VERSION,
)
from backend.app.services.object_runtime.composition_graph_service_core.contracts import (
    build_diagnostic,
)


def build_compile_graph_payload(
    workspace_id: str,
    request: CompositionGraphCompileRequest,
    get_draft: Callable[[str, str], CompositionGraphDraftResponse],
) -> tuple[List[CompositionGraphNode], List[CompositionGraphEdge], Optional[str], Dict[str, Any]]:
    if request.draft_id:
        draft = get_draft(workspace_id, request.draft_id).draft
        nodes = request.nodes if request.nodes is not None else draft.nodes
        edges = request.edges if request.edges is not None else draft.edges
        selected_primary_pack = request.selected_primary_pack or draft.selected_primary_pack
        graph_ref = {
            "draft_id": draft.id,
            "graph_id": draft.graph_id,
            "schema_version": draft.schema_version,
        }
        return list(nodes), list(edges), selected_primary_pack, graph_ref

    graph_id = request.graph_id or f"cg_{uuid.uuid4().hex}"
    return (
        list(request.nodes or []),
        list(request.edges or []),
        request.selected_primary_pack,
        {"graph_id": graph_id, "schema_version": COMPOSITION_GRAPH_SCHEMA_VERSION},
    )


def build_run_graph_payload(
    workspace_id: str,
    request: CompositionGraphRunRequest,
    get_draft: Callable[[str, str], CompositionGraphDraftResponse],
) -> tuple[List[CompositionGraphNode], List[CompositionGraphEdge], Dict[str, Any]]:
    if request.draft_id:
        draft = get_draft(workspace_id, request.draft_id).draft
        nodes = request.nodes if request.nodes is not None else draft.nodes
        edges = request.edges if request.edges is not None else draft.edges
        return (
            list(nodes),
            list(edges),
            {
                "draft_id": draft.id,
                "graph_id": draft.graph_id,
                "schema_version": draft.schema_version,
            },
        )
    graph_id = request.graph_id or f"cg_{uuid.uuid4().hex}"
    return (
        list(request.nodes or []),
        list(request.edges or []),
        {"graph_id": graph_id, "schema_version": COMPOSITION_GRAPH_SCHEMA_VERSION},
    )


def build_initial_run(
    *,
    workspace_id: str,
    request: CompositionGraphRunRequest,
    graph_ref: Dict[str, Any],
    graph_nodes: Sequence[CompositionGraphNode],
    graph_edges: Sequence[CompositionGraphEdge],
    diagnostics: Sequence[CompositionGraphDiagnostic],
) -> CompositionGraphRun:
    graph_run_id = f"cg_run_{uuid.uuid4().hex}"
    now = utc_iso()
    return CompositionGraphRun(
        id=graph_run_id,
        graph_id=str(graph_ref["graph_id"]),
        draft_id=graph_ref.get("draft_id") or request.draft_id,
        workspace_id=workspace_id,
        status="pending",
        meeting_id=request.meeting_id,
        thread_id=request.thread_id,
        command=request.command,
        nodes=list(graph_nodes),
        edges=list(graph_edges),
        node_states={
            node.id: CompositionGraphRunNodeState(
                node_id=node.id,
                node_type=node.type,
            )
            for node in graph_nodes
        },
        diagnostics=list(diagnostics),
        created_at=now,
        updated_at=now,
        metadata={
            **request.metadata,
            "composition_graph_ref": graph_ref,
        },
    )


def normalize_node_options_response(
    *,
    workspace_id: str,
    node_type: str,
    field: str,
    result: Any,
) -> CompositionGraphNodeOptionsResponse:
    if isinstance(result, CompositionGraphNodeOptionsResponse):
        return result
    if isinstance(result, list):
        raw_options = result
        raw_diagnostics: List[Any] = []
        metadata: Dict[str, Any] = {}
    elif isinstance(result, dict):
        raw_options = list(result.get("options") or [])
        raw_diagnostics = list(result.get("diagnostics") or [])
        metadata = dict(result.get("metadata") or {})
    else:
        return CompositionGraphNodeOptionsResponse(
            workspace_id=workspace_id,
            node_type=node_type,
            field=field,
            diagnostics=[
                build_diagnostic(
                    "invalid_node_option_source_result",
                    "Node option source must return an object or list.",
                )
            ],
        )
    options = [
        item
        if isinstance(item, CompositionGraphNodeOption)
        else CompositionGraphNodeOption.model_validate(item)
        for item in raw_options
        if isinstance(item, (dict, CompositionGraphNodeOption))
    ]
    diagnostics = [
        item
        if isinstance(item, CompositionGraphDiagnostic)
        else CompositionGraphDiagnostic.model_validate(item)
        for item in raw_diagnostics
        if isinstance(item, (dict, CompositionGraphDiagnostic))
    ]
    return CompositionGraphNodeOptionsResponse(
        workspace_id=workspace_id,
        node_type=node_type,
        field=field,
        options=options,
        diagnostics=diagnostics,
        metadata=metadata,
    )


def normalize_compile_result(
    *,
    workspace_id: str,
    request: CompositionGraphCompileRequest,
    selected_primary_pack: str,
    graph_ref: Dict[str, Any],
    result: Any,
) -> CompositionGraphCompileResponse:
    if not isinstance(result, dict):
        return CompositionGraphCompileResponse(
            workspace_id=workspace_id,
            status="failed",
            diagnostics=[
                build_diagnostic(
                    "invalid_compile_result",
                    "Pack compile callable must return an object.",
                )
            ],
        )

    raw_diagnostics = result.get("diagnostics") or []
    diagnostics = [
        item
        if isinstance(item, CompositionGraphDiagnostic)
        else CompositionGraphDiagnostic.model_validate(item)
        for item in raw_diagnostics
        if isinstance(item, (dict, CompositionGraphDiagnostic))
    ]
    if str(result.get("status") or "succeeded") == "failed":
        return CompositionGraphCompileResponse(
            workspace_id=workspace_id,
            status="failed",
            diagnostics=diagnostics,
            metadata=dict(result.get("metadata") or {}),
        )

    raw_envelope = (
        result.get("command_envelope")
        or result.get("meeting_command_envelope")
        or {}
    )
    if not isinstance(raw_envelope, dict):
        raw_envelope = {}
    requested_action = raw_envelope.get("requested_action")
    if not isinstance(requested_action, dict):
        requested_action = {
            "verb": "compile_composition_graph",
            "pack_code": selected_primary_pack,
            "parameters": {
                "selected_pack_tool": request.selected_pack_tool,
                "action_parameters": request.action_parameters,
                "composition_graph_ref": graph_ref,
            },
        }
    envelope = CompositionGraphCommandEnvelopeDraft(
        meeting_id=str(raw_envelope.get("meeting_id") or request.meeting_id),
        thread_id=raw_envelope.get("thread_id") or request.thread_id,
        intent_text=str(raw_envelope.get("intent_text") or request.command),
        context_objects=request.context_objects,
        meeting_mentions=list(raw_envelope.get("meeting_mentions") or request.meeting_mentions),
        requested_action=requested_action,
        metadata={
            **dict(raw_envelope.get("metadata") or {}),
            "composition_graph_ref": graph_ref,
            "selected_primary_pack": selected_primary_pack,
        },
    )
    return CompositionGraphCompileResponse(
        workspace_id=workspace_id,
        status="succeeded",
        diagnostics=diagnostics,
        command_envelope=envelope,
        metadata=dict(result.get("metadata") or {}),
    )
