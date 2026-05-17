"""Installed executable composition graph node registry."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import yaml

from backend.app.models.object_runtime import (
    CompositionGraphDiagnostic,
    CompositionGraphNodeProviderContract,
    CompositionGraphNodeProviderNode,
)

CORE_OBJECT_REFERENCE_NODE_TYPE = "object_reference"
_SUPPORTED_LOCK_TOKEN = re.compile(r"{([^{}]+)}")


def _diagnostic(
    code: str,
    message: str,
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> CompositionGraphDiagnostic:
    return CompositionGraphDiagnostic(
        code=code,
        message=message,
        severity="error",
        metadata=metadata or {},
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


def iter_installed_capability_manifests(
    *,
    local_core_root: Path,
    installed_pack_ids: Optional[Iterable[str]] = None,
    capabilities_dir: Optional[Path] = None,
) -> List[Tuple[str, str, Path, Dict[str, Any]]]:
    root = capabilities_dir or resolve_capabilities_dir(local_core_root)
    installed = set(installed_pack_ids) if installed_pack_ids is not None else None
    records: List[Tuple[str, str, Path, Dict[str, Any]]] = []
    if not root.is_dir():
        return records

    for cap_dir in sorted(root.iterdir(), key=lambda path: path.name):
        if not cap_dir.is_dir() or cap_dir.name.startswith((".", "_")):
            continue
        manifest_path = cap_dir / "manifest.yaml"
        if not manifest_path.exists():
            continue
        with manifest_path.open("r", encoding="utf-8") as handle:
            manifest = yaml.safe_load(handle) or {}
        capability_code = str(manifest.get("code") or cap_dir.name).strip()
        pack_id = str(manifest.get("id") or capability_code).strip()
        if installed is not None and capability_code not in installed and pack_id not in installed:
            continue
        records.append((capability_code, pack_id, manifest_path, manifest))
    return records


def load_installed_composition_graph_node_providers(
    *,
    local_core_root: Path,
    installed_pack_ids: Optional[Iterable[str]] = None,
    capabilities_dir: Optional[Path] = None,
) -> tuple[List[CompositionGraphNodeProviderContract], List[CompositionGraphDiagnostic]]:
    providers: List[CompositionGraphNodeProviderContract] = []
    diagnostics: List[CompositionGraphDiagnostic] = []

    try:
        records = iter_installed_capability_manifests(
            local_core_root=local_core_root,
            installed_pack_ids=installed_pack_ids,
            capabilities_dir=capabilities_dir,
        )
    except Exception as exc:
        return [], [
            _diagnostic(
                "manifest_read_failed",
                f"Failed to read installed capability manifests: {exc}",
            )
        ]

    for capability_code, _pack_id, manifest_path, manifest in records:
        raw_contract = manifest.get("composition_graph_nodes")
        if not isinstance(raw_contract, dict) or raw_contract.get("enabled") is not True:
            continue

        raw_nodes: List[Dict[str, Any]] = []
        for raw_node in raw_contract.get("nodes") or []:
            if not isinstance(raw_node, dict):
                continue
            node_id = str(raw_node.get("id") or "").strip()
            if node_id == CORE_OBJECT_REFERENCE_NODE_TYPE:
                diagnostics.append(
                    _diagnostic(
                        "invalid_composition_graph_node_provider",
                        "object_reference is core-owned and cannot be declared by packs",
                        metadata={
                            "capability_code": capability_code,
                            "manifest_path": str(manifest_path),
                        },
                    )
                )
                continue
            normalized_node = {
                **raw_node,
                "source": "pack",
                "capability_code": capability_code,
            }
            raw_nodes.append(normalized_node)

        try:
            provider = CompositionGraphNodeProviderContract(
                capability_code=capability_code,
                label=str(
                    raw_contract.get("label")
                    or manifest.get("name")
                    or capability_code
                ),
                enabled=True,
                contract_version=str(raw_contract.get("contract_version") or "1.0.0"),
                nodes=[
                    _validate_provider_node(
                        capability_code=capability_code,
                        manifest_path=manifest_path,
                        raw_node=raw_node,
                    )
                    for raw_node in raw_nodes
                ],
                metadata=dict(raw_contract.get("metadata") or {}),
            )
        except Exception as exc:
            diagnostics.append(
                _diagnostic(
                    "invalid_composition_graph_node_provider",
                    str(exc),
                    metadata={
                        "capability_code": capability_code,
                        "manifest_path": str(manifest_path),
                    },
                )
            )
            continue
        providers.append(provider)
    return providers, diagnostics


def build_provider_node_map(
    providers: Iterable[CompositionGraphNodeProviderContract],
) -> Dict[str, CompositionGraphNodeProviderNode]:
    node_map: Dict[str, CompositionGraphNodeProviderNode] = {}
    for provider in providers:
        for node in provider.nodes:
            node_map[node.id] = node
    return node_map


def render_runtime_lock_key(
    template: str,
    *,
    workspace_id: str,
    payload: Dict[str, Any],
) -> str:
    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        if token == "workspace_id":
            return workspace_id
        if token.startswith("payload."):
            field = token.removeprefix("payload.")
            value = payload.get(field)
            return "" if value is None else str(value)
        raise ValueError(f"unsupported runtime_lock token: {token}")

    return _SUPPORTED_LOCK_TOKEN.sub(replace, template)


def _validate_provider_node(
    *,
    capability_code: str,
    manifest_path: Path,
    raw_node: Dict[str, Any],
) -> CompositionGraphNodeProviderNode:
    node = CompositionGraphNodeProviderNode.model_validate(raw_node)
    _validate_owned_backend(
        capability_code=capability_code,
        backend=node.executor.backend,
        manifest_path=manifest_path,
    )
    for option_source in node.option_sources.values():
        _validate_owned_backend(
            capability_code=capability_code,
            backend=option_source.backend,
            manifest_path=manifest_path,
        )
    if node.runtime_lock:
        _validate_runtime_lock_template(node.runtime_lock.key_template)
    return node


def _validate_owned_backend(
    *,
    capability_code: str,
    backend: str,
    manifest_path: Path,
) -> None:
    expected_prefix = f"capabilities.{capability_code}."
    if not backend.startswith(expected_prefix) or ":" not in backend:
        raise ValueError(
            "composition_graph_nodes backend must be pack-owned "
            f"({expected_prefix}...): {manifest_path}"
        )


def _validate_runtime_lock_template(template: str) -> None:
    for match in _SUPPORTED_LOCK_TOKEN.finditer(template):
        token = match.group(1)
        if token == "workspace_id":
            continue
        if token.startswith("payload.") and len(token.removeprefix("payload.")) > 0:
            continue
        raise ValueError("runtime_lock.key_template uses an unsupported token")
