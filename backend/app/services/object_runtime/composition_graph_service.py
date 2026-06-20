"""Generic composition graph service for pack-pluggable workbench flows."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Iterable, List, Optional, Sequence

from fastapi import HTTPException

from backend.app.models.object_runtime import (
    CompositionGraphCompileRequest,
    CompositionGraphCompileResponse,
    CompositionGraphContractsResponse,
    CompositionGraphDiagnostic,
    CompositionGraphDraft,
    CompositionGraphDraftCreateRequest,
    CompositionGraphDraftListResponse,
    CompositionGraphDraftResponse,
    CompositionGraphDraftUpdateRequest,
    CompositionGraphEdge,
    CompositionGraphImportExportPayload,
    CompositionGraphImportRequest,
    CompositionGraphImportResponse,
    CompositionGraphNode,
    CompositionGraphNodeOptionsResponse,
    CompositionGraphRunRequest,
    CompositionGraphRunResponse,
    CompositionGraphRunResumeRequest,
)
from backend.app.services.object_runtime.common import _invoke_backend_callable
from backend.app.services.object_runtime.composition_graph_node_registry import (
    build_provider_node_map,
    load_installed_composition_graph_node_providers,
)
from backend.app.services.object_runtime.composition_graph_run_reconciler import (
    reconcile_interrupted_graph_run,
)
from backend.app.services.object_runtime.composition_graph_run_store import (
    CompositionGraphRunStore,
    utc_iso,
)
from backend.app.services.object_runtime.composition_graph_service_core.constants import (
    COMPOSITION_GRAPH_DRAFT_KIND,
    COMPOSITION_GRAPH_SCHEMA_VERSION,
    CORE_OBJECT_REFERENCE_NODE_TYPE,
)
from backend.app.services.object_runtime.composition_graph_service_core.contracts import (
    build_contracts_response,
    build_core_object_reference_node_type,
    build_diagnostic as _diagnostic,
    load_installed_composition_graph_contracts,
)
from backend.app.services.object_runtime.composition_graph_service_core.drafts import (
    artifact_to_draft,
    checksum,
    create_artifact_for_draft,
    draft_storage_payload,
    draft_to_export_payload,
)
from backend.app.services.object_runtime.composition_graph_service_core.payloads import (
    build_compile_graph_payload,
    build_initial_run,
    build_run_graph_payload,
    normalize_compile_result,
    normalize_node_options_response,
)
from backend.app.services.object_runtime.composition_graph_service_core.runs import (
    schedule_graph_run,
)
from backend.app.services.object_runtime.composition_graph_service_core.validation import (
    validate_composition_graph,
)


class CompositionGraphService:
    """Storage, validation, import/export, and compile facade for graph drafts."""

    def __init__(
        self,
        *,
        artifacts_store: Any,
        local_core_root: Path,
        installed_pack_ids: Optional[Iterable[str]] = None,
        capabilities_dir: Optional[Path] = None,
    ) -> None:
        self.artifacts_store = artifacts_store
        self.local_core_root = local_core_root
        self.installed_pack_ids = list(installed_pack_ids) if installed_pack_ids is not None else None
        self.capabilities_dir = capabilities_dir

    def list_contracts(self, workspace_id: str) -> CompositionGraphContractsResponse:
        return build_contracts_response(
            workspace_id=workspace_id,
            local_core_root=self.local_core_root,
            installed_pack_ids=self.installed_pack_ids,
            capabilities_dir=self.capabilities_dir,
        )

    def create_draft(
        self,
        workspace_id: str,
        request: CompositionGraphDraftCreateRequest,
    ) -> CompositionGraphDraftResponse:
        draft_id = f"cg_draft_{uuid.uuid4().hex}"
        graph_id = f"cg_{uuid.uuid4().hex}"
        draft = CompositionGraphDraft(
            id=draft_id,
            graph_id=graph_id,
            workspace_id=workspace_id,
            title=request.title,
            meeting_id=request.meeting_id,
            thread_id=request.thread_id,
            selected_primary_pack=request.selected_primary_pack,
            nodes=request.nodes,
            edges=request.edges,
            viewport=request.viewport,
            metadata=request.metadata,
        )
        create_artifact_for_draft(self.artifacts_store, draft)
        return CompositionGraphDraftResponse(workspace_id=workspace_id, draft=draft)

    def list_drafts(
        self,
        workspace_id: str,
        *,
        thread_id: Optional[str] = None,
        limit: int = 100,
    ) -> CompositionGraphDraftListResponse:
        if thread_id:
            artifacts = list(self.artifacts_store.get_by_thread(workspace_id, thread_id, limit))
        else:
            artifacts = list(self.artifacts_store.list_artifacts_by_workspace(workspace_id, limit=limit))
        drafts = [
            draft
            for artifact in artifacts
            if (draft := artifact_to_draft(artifact)) is not None
        ]
        return CompositionGraphDraftListResponse(workspace_id=workspace_id, drafts=drafts)

    def get_draft(self, workspace_id: str, draft_id: str) -> CompositionGraphDraftResponse:
        artifact = self.artifacts_store.get_artifact(draft_id)
        draft = artifact_to_draft(artifact) if artifact else None
        if draft is None or draft.workspace_id != workspace_id:
            raise HTTPException(status_code=404, detail="Composition graph draft not found")
        return CompositionGraphDraftResponse(workspace_id=workspace_id, draft=draft)

    def update_draft(
        self,
        workspace_id: str,
        draft_id: str,
        request: CompositionGraphDraftUpdateRequest,
    ) -> CompositionGraphDraftResponse:
        current = self.get_draft(workspace_id, draft_id).draft
        update_payload = request.model_dump(exclude_unset=True)
        draft = current.model_copy(update=update_payload)
        content, metadata = draft_storage_payload(draft)
        updated = self.artifacts_store.update_artifact(
            draft_id,
            title=draft.title,
            summary=f"Composition graph draft for {draft.title}",
            thread_id=draft.thread_id,
            content=content,
            metadata=metadata,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Composition graph draft not found")
        return CompositionGraphDraftResponse(workspace_id=workspace_id, draft=draft)

    def export_draft(
        self,
        workspace_id: str,
        draft_id: str,
    ) -> CompositionGraphImportExportPayload:
        draft = self.get_draft(workspace_id, draft_id).draft
        payload = draft_to_export_payload(draft)
        payload.metadata["export_checksum"] = checksum(payload.model_dump(mode="json"))
        return payload

    def import_graph(
        self,
        workspace_id: str,
        request: CompositionGraphImportRequest,
    ) -> CompositionGraphImportResponse:
        diagnostics = self.validate_graph(
            nodes=request.graph.nodes,
            edges=request.graph.edges,
            selected_primary_pack=request.graph.selected_primary_pack,
            require_primary=False,
        )
        if diagnostics:
            return CompositionGraphImportResponse(
                workspace_id=workspace_id,
                valid=False,
                diagnostics=diagnostics,
            )
        if not request.persist:
            return CompositionGraphImportResponse(workspace_id=workspace_id, valid=True)
        create_response = self.create_draft(
            workspace_id,
            CompositionGraphDraftCreateRequest(
                title=request.graph.title,
                meeting_id=request.meeting_id,
                thread_id=request.thread_id,
                selected_primary_pack=request.graph.selected_primary_pack,
                nodes=request.graph.nodes,
                edges=request.graph.edges,
                viewport=request.graph.viewport,
                metadata=request.graph.metadata,
            ),
        )
        return CompositionGraphImportResponse(
            workspace_id=workspace_id,
            valid=True,
            draft=create_response.draft,
        )

    async def compile_graph(
        self,
        workspace_id: str,
        request: CompositionGraphCompileRequest,
    ) -> CompositionGraphCompileResponse:
        graph_nodes, graph_edges, selected_primary_pack, graph_ref = build_compile_graph_payload(
            workspace_id,
            request,
            self.get_draft,
        )
        diagnostics = self.validate_graph(
            nodes=graph_nodes,
            edges=graph_edges,
            selected_primary_pack=selected_primary_pack,
            require_primary=True,
        )
        if diagnostics:
            return CompositionGraphCompileResponse(
                workspace_id=workspace_id,
                status="failed",
                diagnostics=diagnostics,
            )

        contracts, contract_diagnostics = load_installed_composition_graph_contracts(
            local_core_root=self.local_core_root,
            installed_pack_ids=self.installed_pack_ids,
            capabilities_dir=self.capabilities_dir,
        )
        contract_by_code = {contract.capability_code: contract for contract in contracts}
        primary_contract = contract_by_code.get(selected_primary_pack or "")
        if primary_contract is None or primary_contract.compile is None:
            return CompositionGraphCompileResponse(
                workspace_id=workspace_id,
                status="failed",
                diagnostics=contract_diagnostics
                + [
                    _diagnostic(
                        "missing_primary_pack",
                        "Selected primary pack does not expose a composition graph contract.",
                    )
                ],
            )

        try:
            invocation_result = await _invoke_backend_callable(
                primary_contract.compile.backend,
                workspace_id=workspace_id,
                meeting_id=request.meeting_id,
                thread_id=request.thread_id,
                command=request.command,
                meeting_mentions=request.meeting_mentions,
                context_objects=[
                    entry.model_dump(mode="json", exclude_none=True)
                    for entry in request.context_objects
                ],
                object_action_entries=[
                    entry.model_dump(mode="json", exclude_none=True)
                    for entry in request.object_action_entries
                ],
                selected_pack_tool=request.selected_pack_tool,
                action_parameters=request.action_parameters,
                selected_primary_pack=selected_primary_pack,
                composition_graph_ref=graph_ref,
                graph={
                    "schema_version": COMPOSITION_GRAPH_SCHEMA_VERSION,
                    "nodes": [node.model_dump(mode="json") for node in graph_nodes],
                    "edges": [edge.model_dump(mode="json") for edge in graph_edges],
                },
            )
        except Exception as exc:
            return CompositionGraphCompileResponse(
                workspace_id=workspace_id,
                status="failed",
                diagnostics=[
                    _diagnostic(
                        "pack_compile_failed",
                        f"Pack compile callable failed: {exc}",
                        metadata={"capability_code": selected_primary_pack or ""},
                    )
                ],
            )
        return normalize_compile_result(
            workspace_id=workspace_id,
            request=request,
            selected_primary_pack=selected_primary_pack or "",
            graph_ref=graph_ref,
            result=invocation_result,
        )

    async def start_run(
        self,
        workspace_id: str,
        request: CompositionGraphRunRequest,
    ) -> CompositionGraphRunResponse:
        graph_nodes, graph_edges, graph_ref = build_run_graph_payload(
            workspace_id,
            request,
            self.get_draft,
        )
        diagnostics = self.validate_graph(
            nodes=graph_nodes,
            edges=graph_edges,
            selected_primary_pack=None,
            require_primary=False,
        )
        run = build_initial_run(
            workspace_id=workspace_id,
            request=request,
            graph_ref=graph_ref,
            graph_nodes=graph_nodes,
            graph_edges=graph_edges,
            diagnostics=diagnostics,
        )
        run_store = CompositionGraphRunStore(self.artifacts_store)
        run_store.create_run(run)
        if diagnostics:
            failed_run = run_store.update_run(
                run.model_copy(
                    update={
                        "status": "failed",
                        "completed_at": utc_iso(),
                    }
                )
            )
            return CompositionGraphRunResponse(workspace_id=workspace_id, run=failed_run)

        running = run_store.update_run(
            run.model_copy(
                update={
                    "status": "running",
                    "started_at": utc_iso(),
                }
            )
        )
        self._schedule_run(running)
        return CompositionGraphRunResponse(workspace_id=workspace_id, run=running)

    def get_run(
        self,
        workspace_id: str,
        graph_run_id: str,
    ) -> CompositionGraphRunResponse:
        run_store = CompositionGraphRunStore(self.artifacts_store)
        run = run_store.get_run(workspace_id, graph_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Composition graph run not found")
        run = reconcile_interrupted_graph_run(run_store=run_store, run=run)
        return CompositionGraphRunResponse(workspace_id=workspace_id, run=run)

    async def resume_run(
        self,
        workspace_id: str,
        graph_run_id: str,
        request: CompositionGraphRunResumeRequest,
    ) -> CompositionGraphRunResponse:
        run_store = CompositionGraphRunStore(self.artifacts_store)
        run = run_store.get_run(workspace_id, graph_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Composition graph run not found")
        if run.status != "waiting":
            raise HTTPException(
                status_code=409,
                detail="Only waiting composition graph runs can be resumed",
            )
        next_run = run.model_copy(
            update={
                "status": "running",
                "command": request.command if request.command is not None else run.command,
                "metadata": {**run.metadata, **request.metadata},
                "completed_at": None,
            }
        )
        next_run = run_store.update_run(next_run)
        self._schedule_run(next_run)
        return CompositionGraphRunResponse(workspace_id=workspace_id, run=next_run)

    async def resolve_node_options(
        self,
        workspace_id: str,
        *,
        node_type: str,
        field: str,
    ) -> CompositionGraphNodeOptionsResponse:
        providers, diagnostics = load_installed_composition_graph_node_providers(
            local_core_root=self.local_core_root,
            installed_pack_ids=self.installed_pack_ids,
            capabilities_dir=self.capabilities_dir,
        )
        provider_node = build_provider_node_map(providers).get(node_type)
        if provider_node is None:
            return CompositionGraphNodeOptionsResponse(
                workspace_id=workspace_id,
                node_type=node_type,
                field=field,
                diagnostics=diagnostics
                + [
                    _diagnostic(
                        "node_option_source_not_found",
                        "Node type does not declare a server-side option source.",
                        metadata={"node_type": node_type, "field": field},
                    )
                ],
            )
        option_source = provider_node.option_sources.get(field)
        if option_source is None:
            return CompositionGraphNodeOptionsResponse(
                workspace_id=workspace_id,
                node_type=node_type,
                field=field,
                diagnostics=diagnostics
                + [
                    _diagnostic(
                        "node_option_source_not_found",
                        "Node field does not declare a server-side option source.",
                        metadata={"node_type": node_type, "field": field},
                    )
                ],
            )
        try:
            result = await _invoke_backend_callable(
                option_source.backend,
                workspace_id=workspace_id,
                node_type=node_type,
                field=field,
            )
        except Exception as exc:
            return CompositionGraphNodeOptionsResponse(
                workspace_id=workspace_id,
                node_type=node_type,
                field=field,
                diagnostics=[
                    _diagnostic(
                        "node_option_source_failed",
                        f"Node option source failed: {exc}",
                        metadata={"node_type": node_type, "field": field},
                    )
                ],
            )
        return normalize_node_options_response(
            workspace_id=workspace_id,
            node_type=node_type,
            field=field,
            result=result,
        )

    def validate_graph(
        self,
        *,
        nodes: Sequence[CompositionGraphNode],
        edges: Sequence[CompositionGraphEdge],
        selected_primary_pack: Optional[str],
        require_primary: bool,
    ) -> List[CompositionGraphDiagnostic]:
        return validate_composition_graph(
            nodes=nodes,
            edges=edges,
            selected_primary_pack=selected_primary_pack,
            require_primary=require_primary,
            contracts_response=self.list_contracts(workspace_id="validation"),
        )

    def _schedule_run(self, run: Any) -> None:
        schedule_graph_run(
            run=run,
            artifacts_store=self.artifacts_store,
            local_core_root=self.local_core_root,
            installed_pack_ids=self.installed_pack_ids,
            capabilities_dir=self.capabilities_dir,
        )
