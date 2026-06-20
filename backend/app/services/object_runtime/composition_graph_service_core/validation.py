"""Validation helpers for composition graph service."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from backend.app.models.object_runtime import (
    CompositionGraphContract,
    CompositionGraphContractsResponse,
    CompositionGraphDiagnostic,
    CompositionGraphEdge,
    CompositionGraphNode,
    CompositionGraphNodeType,
    CompositionGraphPort,
)
from backend.app.models.object_runtime.refs import ObjectRef
from backend.app.services.object_runtime.composition_graph_service_core.constants import (
    CORE_OBJECT_REFERENCE_NODE_TYPE,
)
from backend.app.services.object_runtime.composition_graph_service_core.contracts import (
    build_core_object_reference_node_type,
    build_diagnostic,
)


def validate_composition_graph(
    *,
    nodes: Sequence[CompositionGraphNode],
    edges: Sequence[CompositionGraphEdge],
    selected_primary_pack: Optional[str],
    require_primary: bool,
    contracts_response: CompositionGraphContractsResponse,
) -> List[CompositionGraphDiagnostic]:
    diagnostics = list(contracts_response.diagnostics)
    contract_by_code = {
        contract.capability_code: contract for contract in contracts_response.contracts
    }
    if require_primary and not selected_primary_pack:
        diagnostics.append(
            build_diagnostic(
                "missing_primary_pack",
                "Compile requires selected_primary_pack.",
            )
        )
    elif (
        selected_primary_pack
        and (
            selected_primary_pack not in contract_by_code
            or (
                require_primary
                and contract_by_code[selected_primary_pack].compile is None
            )
        )
    ):
        diagnostics.append(
            build_diagnostic(
                "missing_primary_pack",
                "Selected primary pack does not expose a composition graph contract.",
                metadata={"selected_primary_pack": selected_primary_pack},
            )
        )

    node_types = node_type_map(contracts_response.contracts)
    node_by_id: Dict[str, CompositionGraphNode] = {}
    for node in nodes:
        if node.id in node_by_id:
            diagnostics.append(
                build_diagnostic("duplicate_node_id", "Node ids must be unique.", node_id=node.id)
            )
            continue
        node_by_id[node.id] = node
        node_type = node_types.get(node.type)
        if node_type is None:
            diagnostics.append(
                build_diagnostic(
                    "unknown_node_type",
                    "Node type is not declared by core or an installed pack contract.",
                    node_id=node.id,
                    metadata={"node_type": node.type},
                )
            )
            continue
        diagnostics.extend(validate_node_payload(node, node_type))

    edge_ids: set[str] = set()
    incoming_by_target_port: set[tuple[str, str]] = set()
    adjacency: Dict[str, List[str]] = {node.id: [] for node in nodes}
    for edge in edges:
        if edge.id in edge_ids:
            diagnostics.append(
                build_diagnostic("duplicate_edge_id", "Edge ids must be unique.", edge_id=edge.id)
            )
            continue
        edge_ids.add(edge.id)
        source = node_by_id.get(edge.source)
        target = node_by_id.get(edge.target)
        if source is None or target is None:
            diagnostics.append(
                build_diagnostic(
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
        source_port = find_port(source_type.output_ports, edge.source_port)
        target_port = find_port(target_type.input_ports, edge.target_port)
        if source_port is None:
            diagnostics.append(
                build_diagnostic(
                    "source_port_missing",
                    "Edge source_port must exist on the source node output ports.",
                    edge_id=edge.id,
                    port_id=edge.source_port,
                )
            )
            continue
        if target_port is None:
            diagnostics.append(
                build_diagnostic(
                    "target_port_missing",
                    "Edge target_port must exist on the target node input ports.",
                    edge_id=edge.id,
                    port_id=edge.target_port,
                )
            )
            continue
        if not data_types_compatible(source_port.data_type, target_port.data_type):
            diagnostics.append(
                build_diagnostic(
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
                    build_diagnostic(
                        "missing_required_input",
                        "Required input port is not connected.",
                        node_id=node.id,
                        port_id=port.id,
                    )
                )

    if has_cycle(adjacency):
        diagnostics.append(
            build_diagnostic("cycle_detected", "Composition graph must be acyclic.")
        )
    return [diagnostic for diagnostic in diagnostics if diagnostic.severity == "error"]


def node_type_map(
    contracts: Sequence[CompositionGraphContract],
) -> Dict[str, CompositionGraphNodeType]:
    node_types = {CORE_OBJECT_REFERENCE_NODE_TYPE: build_core_object_reference_node_type()}
    for contract in contracts:
        for node_type in contract.node_types:
            node_types[node_type.id] = node_type
    return node_types


def validate_node_payload(
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
                build_diagnostic(
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
                build_diagnostic(
                    "invalid_node_payload",
                    f"Node payload does not match its payload_schema: {exc}",
                    node_id=node.id,
                )
            )
    return diagnostics


def find_port(
    ports: Sequence[CompositionGraphPort],
    port_id: str,
) -> Optional[CompositionGraphPort]:
    return next((port for port in ports if port.id == port_id), None)


def data_types_compatible(source_type: str, target_type: str) -> bool:
    return "any" in {source_type, target_type} or source_type == target_type


def has_cycle(adjacency: Dict[str, List[str]]) -> bool:
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
