"""Generic composition graph service for pack-pluggable workbench flows."""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import yaml
from fastapi import HTTPException
from fastapi.encoders import jsonable_encoder

from backend.app.models.object_runtime import (
    CompositionGraphCommandEnvelopeDraft,
    CompositionGraphCompileRequest,
    CompositionGraphCompileResponse,
    CompositionGraphContract,
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
    CompositionGraphNodeType,
    CompositionGraphPort,
    CompositionGraphViewport,
)
from backend.app.models.object_runtime.refs import ObjectRef
from backend.app.models.workspace import Artifact, ArtifactType, PrimaryActionType
from backend.app.services.object_runtime.common import _invoke_backend_callable
from backend.app.services.object_runtime.composition_graph_io import (
    sanitize_composition_graph_export_payload,
)
from backend.app.services.object_runtime.composition_graph_migrations import (
    upgrade_composition_graph_content,
)

COMPOSITION_GRAPH_SCHEMA_VERSION = "composition_graph.v1"
COMPOSITION_GRAPH_DRAFT_KIND = "composition_graph_draft"
CORE_OBJECT_REFERENCE_NODE_TYPE = "object_reference"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _diagnostic(
    code: str,
    message: str,
    *,
    node_id: str | None = None,
    edge_id: str | None = None,
    port_id: str | None = None,
    severity: str = "error",
    metadata: Optional[Dict[str, Any]] = None,
) -> CompositionGraphDiagnostic:
    return CompositionGraphDiagnostic(
        code=code,
        message=message,
        severity=severity,  # type: ignore[arg-type]
        node_id=node_id,
        edge_id=edge_id,
        port_id=port_id,
        metadata=metadata or {},
    )


def build_core_object_reference_node_type() -> CompositionGraphNodeType:
    return CompositionGraphNodeType(
        id=CORE_OBJECT_REFERENCE_NODE_TYPE,
        label="Object Reference",
        source="core",
        category="context",
        description="Generic reference to a canonical Addressable Object.",
        output_ports=[
            CompositionGraphPort(
                id="object",
                direction="output",
                label="Object",
                data_type="object_ref",
            )
        ],
        payload_schema={
            "type": "object",
            "required": ["ref"],
            "properties": {
                "ref": {
                    "type": "object",
                    "required": ["uri", "owner_pack", "object_kind", "object_id"],
                    "properties": {
                        "uri": {"type": "string"},
                        "owner_pack": {"type": "string"},
                        "object_kind": {"type": "string"},
                        "object_id": {"type": "string"},
                        "workspace_id": {"type": "string"},
                    },
                    "additionalProperties": True,
                }
            },
            "additionalProperties": True,
        },
    )


def _resolve_capabilities_dir(local_core_root: Path) -> Path:
    candidates = [
        local_core_root / "backend" / "app" / "capabilities",
        local_core_root / "app" / "capabilities",
        Path("/app/backend/app/capabilities"),
    ]
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


def load_installed_composition_graph_contracts(
    *,
    local_core_root: Path,
    installed_pack_ids: Optional[Iterable[str]] = None,
    capabilities_dir: Optional[Path] = None,
) -> tuple[List[CompositionGraphContract], List[CompositionGraphDiagnostic]]:
    """Load composition graph contracts from installed capability manifests."""

    root = capabilities_dir or _resolve_capabilities_dir(local_core_root)
    installed = set(installed_pack_ids) if installed_pack_ids is not None else None
    contracts: List[CompositionGraphContract] = []
    diagnostics: List[CompositionGraphDiagnostic] = []
    if not root.is_dir():
        return contracts, diagnostics

    for cap_dir in sorted(root.iterdir(), key=lambda path: path.name):
        if not cap_dir.is_dir() or cap_dir.name.startswith((".", "_")):
            continue
        manifest_path = cap_dir / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            with manifest_path.open("r", encoding="utf-8") as handle:
                manifest = yaml.safe_load(handle) or {}
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    "manifest_read_failed",
                    f"Failed to read composition graph manifest: {exc}",
                    metadata={"manifest_path": str(manifest_path)},
                )
            )
            continue

        capability_code = str(manifest.get("code") or cap_dir.name).strip()
        pack_id = str(manifest.get("id") or capability_code).strip()
        if installed is not None and capability_code not in installed and pack_id not in installed:
            continue

        raw_contract = manifest.get("composition_graph")
        if not isinstance(raw_contract, dict) or raw_contract.get("enabled") is not True:
            continue

        raw_node_types = []
        for raw_node_type in raw_contract.get("node_types") or []:
            if not isinstance(raw_node_type, dict):
                continue
            normalized_node_type = {
                **raw_node_type,
                "source": "pack",
                "capability_code": capability_code,
            }
            raw_node_types.append(normalized_node_type)

        try:
            contracts.append(
                CompositionGraphContract(
                    capability_code=capability_code,
                    label=str(
                        raw_contract.get("label")
                        or manifest.get("name")
                        or capability_code
                    ),
                    enabled=True,
                    contract_version=str(raw_contract.get("contract_version") or "1.0.0"),
                    accepted_object_roles=list(raw_contract.get("accepted_object_roles") or []),
                    node_types=raw_node_types,
                    edge_types=list(raw_contract.get("edge_types") or []),
                    compile=raw_contract.get("compile") or {},
                    metadata=dict(raw_contract.get("metadata") or {}),
                )
            )
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    "invalid_composition_graph_contract",
                    str(exc),
                    metadata={
                        "capability_code": capability_code,
                        "manifest_path": str(manifest_path),
                    },
                )
            )
    return contracts, diagnostics


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
        contracts, diagnostics = load_installed_composition_graph_contracts(
            local_core_root=self.local_core_root,
            installed_pack_ids=self.installed_pack_ids,
            capabilities_dir=self.capabilities_dir,
        )
        return CompositionGraphContractsResponse(
            workspace_id=workspace_id,
            contracts=contracts,
            diagnostics=diagnostics,
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
        self._create_artifact_for_draft(draft)
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
            if (draft := self._artifact_to_draft(artifact)) is not None
        ]
        return CompositionGraphDraftListResponse(workspace_id=workspace_id, drafts=drafts)

    def get_draft(self, workspace_id: str, draft_id: str) -> CompositionGraphDraftResponse:
        artifact = self.artifacts_store.get_artifact(draft_id)
        draft = self._artifact_to_draft(artifact) if artifact else None
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
        content, metadata = self._draft_storage_payload(draft)
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
        payload = self._draft_to_export_payload(draft)
        payload.metadata["export_checksum"] = self._checksum(payload.model_dump(mode="json"))
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
        graph_nodes, graph_edges, selected_primary_pack, graph_ref = self._compile_graph_payload(
            workspace_id,
            request,
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
        if primary_contract is None:
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
        return self._normalize_compile_result(
            workspace_id=workspace_id,
            request=request,
            selected_primary_pack=selected_primary_pack or "",
            graph_ref=graph_ref,
            result=invocation_result,
        )

    def validate_graph(
        self,
        *,
        nodes: Sequence[CompositionGraphNode],
        edges: Sequence[CompositionGraphEdge],
        selected_primary_pack: Optional[str],
        require_primary: bool,
    ) -> List[CompositionGraphDiagnostic]:
        contracts_response = self.list_contracts(workspace_id="validation")
        diagnostics = list(contracts_response.diagnostics)
        contract_by_code = {
            contract.capability_code: contract for contract in contracts_response.contracts
        }
        if require_primary and not selected_primary_pack:
            diagnostics.append(
                _diagnostic(
                    "missing_primary_pack",
                    "Compile requires selected_primary_pack.",
                )
            )
        elif selected_primary_pack and selected_primary_pack not in contract_by_code:
            diagnostics.append(
                _diagnostic(
                    "missing_primary_pack",
                    "Selected primary pack does not expose a composition graph contract.",
                    metadata={"selected_primary_pack": selected_primary_pack},
                )
            )

        node_types = self._node_type_map(contracts_response.contracts)
        node_by_id: Dict[str, CompositionGraphNode] = {}
        for node in nodes:
            if node.id in node_by_id:
                diagnostics.append(
                    _diagnostic("duplicate_node_id", "Node ids must be unique.", node_id=node.id)
                )
                continue
            node_by_id[node.id] = node
            node_type = node_types.get(node.type)
            if node_type is None:
                diagnostics.append(
                    _diagnostic(
                        "unknown_node_type",
                        "Node type is not declared by core or an installed pack contract.",
                        node_id=node.id,
                        metadata={"node_type": node.type},
                    )
                )
                continue
            diagnostics.extend(self._validate_node_payload(node, node_type))

        edge_ids: set[str] = set()
        incoming_by_target_port: set[tuple[str, str]] = set()
        adjacency: Dict[str, List[str]] = {node.id: [] for node in nodes}
        for edge in edges:
            if edge.id in edge_ids:
                diagnostics.append(
                    _diagnostic("duplicate_edge_id", "Edge ids must be unique.", edge_id=edge.id)
                )
                continue
            edge_ids.add(edge.id)
            source = node_by_id.get(edge.source)
            target = node_by_id.get(edge.target)
            if source is None or target is None:
                diagnostics.append(
                    _diagnostic(
                        "edge_endpoint_missing",
                        "Edge source and target nodes must exist.",
                        edge_id=edge.id,
                    )
                )
                continue
            source_type = node_types.get(source.type)
            target_type = node_types.get(target.type)
            if source_type is None or target_type is None:
                continue
            source_port = self._find_port(source_type.output_ports, edge.source_port)
            target_port = self._find_port(target_type.input_ports, edge.target_port)
            if source_port is None:
                diagnostics.append(
                    _diagnostic(
                        "source_port_missing",
                        "Edge source_port must exist on the source node output ports.",
                        edge_id=edge.id,
                        port_id=edge.source_port,
                    )
                )
                continue
            if target_port is None:
                diagnostics.append(
                    _diagnostic(
                        "target_port_missing",
                        "Edge target_port must exist on the target node input ports.",
                        edge_id=edge.id,
                        port_id=edge.target_port,
                    )
                )
                continue
            if not self._data_types_compatible(source_port.data_type, target_port.data_type):
                diagnostics.append(
                    _diagnostic(
                        "port_type_mismatch",
                        "Edge port data types are not compatible.",
                        edge_id=edge.id,
                        metadata={
                            "source_data_type": source_port.data_type,
                            "target_data_type": target_port.data_type,
                        },
                    )
                )
            incoming_by_target_port.add((edge.target, edge.target_port))
            adjacency.setdefault(edge.source, []).append(edge.target)

        for node in nodes:
            node_type = node_types.get(node.type)
            if node_type is None:
                continue
            for port in node_type.input_ports:
                if port.required and (node.id, port.id) not in incoming_by_target_port:
                    diagnostics.append(
                        _diagnostic(
                            "missing_required_input",
                            "Required input port is not connected.",
                            node_id=node.id,
                            port_id=port.id,
                        )
                    )

        if self._has_cycle(adjacency):
            diagnostics.append(
                _diagnostic("cycle_detected", "Composition graph must be acyclic.")
            )
        return [diagnostic for diagnostic in diagnostics if diagnostic.severity == "error"]

    def _node_type_map(
        self,
        contracts: Sequence[CompositionGraphContract],
    ) -> Dict[str, CompositionGraphNodeType]:
        node_types = {CORE_OBJECT_REFERENCE_NODE_TYPE: build_core_object_reference_node_type()}
        for contract in contracts:
            for node_type in contract.node_types:
                node_types[node_type.id] = node_type
        return node_types

    def _validate_node_payload(
        self,
        node: CompositionGraphNode,
        node_type: CompositionGraphNodeType,
    ) -> List[CompositionGraphDiagnostic]:
        diagnostics: List[CompositionGraphDiagnostic] = []
        if node.type == CORE_OBJECT_REFERENCE_NODE_TYPE:
            raw_ref = node.payload.get("ref")
            try:
                ObjectRef.model_validate(raw_ref)
            except Exception as exc:
                diagnostics.append(
                    _diagnostic(
                        "invalid_object_reference",
                        f"object_reference payload requires a valid ObjectRef: {exc}",
                        node_id=node.id,
                    )
                )
        if node_type.payload_schema:
            try:
                import jsonschema

                jsonschema.validate(node.payload, node_type.payload_schema)
            except Exception as exc:
                diagnostics.append(
                    _diagnostic(
                        "invalid_node_payload",
                        f"Node payload does not match its payload_schema: {exc}",
                        node_id=node.id,
                    )
                )
        return diagnostics

    @staticmethod
    def _find_port(
        ports: Sequence[CompositionGraphPort],
        port_id: str,
    ) -> Optional[CompositionGraphPort]:
        return next((port for port in ports if port.id == port_id), None)

    @staticmethod
    def _data_types_compatible(source_type: str, target_type: str) -> bool:
        return "any" in {source_type, target_type} or source_type == target_type

    @staticmethod
    def _has_cycle(adjacency: Dict[str, List[str]]) -> bool:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            for target_id in adjacency.get(node_id, []):
                if visit(target_id):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(visit(node_id) for node_id in adjacency)

    def _compile_graph_payload(
        self,
        workspace_id: str,
        request: CompositionGraphCompileRequest,
    ) -> tuple[List[CompositionGraphNode], List[CompositionGraphEdge], Optional[str], Dict[str, Any]]:
        if request.draft_id:
            draft = self.get_draft(workspace_id, request.draft_id).draft
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

    def _normalize_compile_result(
        self,
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
                    _diagnostic(
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

    def _create_artifact_for_draft(self, draft: CompositionGraphDraft) -> None:
        content, metadata = self._draft_storage_payload(draft)
        artifact = Artifact(
            id=draft.id,
            workspace_id=draft.workspace_id,
            intent_id=None,
            task_id=None,
            execution_id=None,
            thread_id=draft.thread_id,
            playbook_code="core.composition_graph",
            artifact_type=ArtifactType.DATA,
            title=draft.title,
            summary=f"Composition graph draft for {draft.title}",
            content=content,
            storage_ref=None,
            sync_state=None,
            primary_action_type=PrimaryActionType.EDIT,
            metadata=metadata,
            created_at=_utc_now(),
            updated_at=_utc_now(),
        )
        self.artifacts_store.create_artifact(artifact)

    def _draft_storage_payload(
        self,
        draft: CompositionGraphDraft,
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        content = {
            "schema_version": draft.schema_version,
            "nodes": [node.model_dump(mode="json") for node in draft.nodes],
            "edges": [edge.model_dump(mode="json") for edge in draft.edges],
            "viewport": draft.viewport.model_dump(mode="json"),
            "selected_primary_pack": draft.selected_primary_pack,
            "history": [entry.model_dump(mode="json") for entry in draft.history],
            "migrations": [entry.model_dump(mode="json") for entry in draft.migrations],
            "node_diagnostics": jsonable_encoder(draft.node_diagnostics),
            "edge_diagnostics": jsonable_encoder(draft.edge_diagnostics),
            "metadata": draft.metadata,
        }
        metadata = {
            "kind": COMPOSITION_GRAPH_DRAFT_KIND,
            "schema_version": draft.schema_version,
            "workspace_id": draft.workspace_id,
            "meeting_id": draft.meeting_id,
            "thread_id": draft.thread_id,
            "graph_id": draft.graph_id,
            "title": draft.title,
        }
        return content, metadata

    def _artifact_to_draft(self, artifact: Any) -> Optional[CompositionGraphDraft]:
        if artifact is None:
            return None
        metadata = dict(getattr(artifact, "metadata", {}) or {})
        if metadata.get("kind") != COMPOSITION_GRAPH_DRAFT_KIND:
            return None
        content = upgrade_composition_graph_content(dict(getattr(artifact, "content", {}) or {}))
        return CompositionGraphDraft(
            id=getattr(artifact, "id"),
            graph_id=str(metadata.get("graph_id") or getattr(artifact, "id")),
            workspace_id=str(metadata.get("workspace_id") or getattr(artifact, "workspace_id")),
            title=str(metadata.get("title") or getattr(artifact, "title", "Composition Graph")),
            schema_version=str(
                content.get("schema_version")
                or metadata.get("schema_version")
                or COMPOSITION_GRAPH_SCHEMA_VERSION
            ),
            meeting_id=metadata.get("meeting_id"),
            thread_id=metadata.get("thread_id") or getattr(artifact, "thread_id", None),
            selected_primary_pack=content.get("selected_primary_pack"),
            nodes=[
                CompositionGraphNode.model_validate(item)
                for item in list(content.get("nodes") or [])
            ],
            edges=[
                CompositionGraphEdge.model_validate(item)
                for item in list(content.get("edges") or [])
            ],
            viewport=CompositionGraphViewport.model_validate(content.get("viewport") or {}),
            history=list(content.get("history") or []),
            migrations=list(content.get("migrations") or []),
            node_diagnostics=dict(content.get("node_diagnostics") or {}),
            edge_diagnostics=dict(content.get("edge_diagnostics") or {}),
            metadata=dict(content.get("metadata") or {}),
        )

    @staticmethod
    def _draft_to_export_payload(
        draft: CompositionGraphDraft,
    ) -> CompositionGraphImportExportPayload:
        return sanitize_composition_graph_export_payload(
            CompositionGraphImportExportPayload(
                schema_version=draft.schema_version,
                graph_id=draft.graph_id,
                title=draft.title,
                selected_primary_pack=draft.selected_primary_pack,
                nodes=draft.nodes,
                edges=draft.edges,
                viewport=draft.viewport,
                metadata=dict(draft.metadata),
            )
        )

    @staticmethod
    def _checksum(payload: Dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()
