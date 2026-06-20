"""Composition graph contract loading helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from backend.app.models.object_runtime import (
    CompositionGraphContract,
    CompositionGraphContractsResponse,
    CompositionGraphDiagnostic,
    CompositionGraphNodeType,
    CompositionGraphPort,
)
from backend.app.services.object_runtime.composition_graph_node_registry import (
    load_installed_composition_graph_node_providers,
    iter_installed_capability_manifests,
)
from backend.app.services.object_runtime.composition_graph_service_core.constants import (
    CORE_OBJECT_REFERENCE_NODE_TYPE,
)


def build_diagnostic(
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


def resolve_capabilities_dir(local_core_root: Path) -> Path:
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

    contracts: List[CompositionGraphContract] = []
    diagnostics: List[CompositionGraphDiagnostic] = []
    try:
        records = iter_installed_capability_manifests(
            local_core_root=local_core_root,
            installed_pack_ids=installed_pack_ids,
            capabilities_dir=capabilities_dir,
        )
    except Exception as exc:
        diagnostics.append(
            build_diagnostic(
                "manifest_read_failed",
                f"Failed to read composition graph manifest: {exc}",
            )
        )
        return contracts, diagnostics

    for capability_code, _pack_id, manifest_path, manifest in records:
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
                build_diagnostic(
                    "invalid_composition_graph_contract",
                    str(exc),
                    metadata={
                        "capability_code": capability_code,
                        "manifest_path": str(manifest_path),
                    },
                )
            )
    return contracts, diagnostics


def build_contracts_response(
    *,
    workspace_id: str,
    local_core_root: Path,
    installed_pack_ids: Optional[Iterable[str]] = None,
    capabilities_dir: Optional[Path] = None,
) -> CompositionGraphContractsResponse:
    contracts, diagnostics = load_installed_composition_graph_contracts(
        local_core_root=local_core_root,
        installed_pack_ids=installed_pack_ids,
        capabilities_dir=capabilities_dir,
    )
    providers, provider_diagnostics = load_installed_composition_graph_node_providers(
        local_core_root=local_core_root,
        installed_pack_ids=installed_pack_ids,
        capabilities_dir=capabilities_dir,
    )
    diagnostics.extend(provider_diagnostics)
    contract_by_code = {contract.capability_code: contract for contract in contracts}
    for provider in providers:
        existing = contract_by_code.get(provider.capability_code)
        provider_node_types = [
            CompositionGraphNodeType.model_validate(
                node.model_dump(
                    mode="json",
                    exclude={"executor", "option_sources", "runtime_lock"},
                )
            )
            for node in provider.nodes
        ]
        if existing is not None:
            existing.node_types.extend(provider_node_types)
            existing.metadata = {
                **existing.metadata,
                "composition_graph_nodes_contract_version": provider.contract_version,
            }
            continue
        provider_contract = CompositionGraphContract(
            capability_code=provider.capability_code,
            label=provider.label,
            enabled=True,
            contract_version=provider.contract_version,
            node_types=provider_node_types,
            edge_types=[],
            compile=None,
            metadata={
                **provider.metadata,
                "contract_kind": "composition_graph_nodes",
            },
        )
        contracts.append(provider_contract)
        contract_by_code[provider.capability_code] = provider_contract
    return CompositionGraphContractsResponse(
        workspace_id=workspace_id,
        contracts=contracts,
        diagnostics=diagnostics,
    )
