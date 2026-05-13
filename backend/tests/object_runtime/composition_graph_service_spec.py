from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest
import yaml

from backend.app.models.object_runtime import (
    CompositionGraphCompileRequest,
    CompositionGraphDraftCreateRequest,
    CompositionGraphEdge,
    CompositionGraphImportExportPayload,
    CompositionGraphImportRequest,
    CompositionGraphNode,
    CompositionGraphViewport,
    ObjectRef,
    ObjectRoleEntry,
)
from backend.app.services.object_runtime.composition_graph_service import (
    CompositionGraphService,
    load_installed_composition_graph_contracts,
)


class MemoryArtifactsStore:
    def __init__(self):
        self.items = {}

    def create_artifact(self, artifact):
        self.items[artifact.id] = artifact
        return artifact

    def get_artifact(self, artifact_id):
        return self.items.get(artifact_id)

    def update_artifact(self, artifact_id, **kwargs):
        artifact = self.items.get(artifact_id)
        if artifact is None:
            return False
        self.items[artifact_id] = artifact.model_copy(update=kwargs)
        return True

    def get_by_thread(self, workspace_id, thread_id, limit=100):
        return [
            artifact
            for artifact in self.items.values()
            if artifact.workspace_id == workspace_id and artifact.thread_id == thread_id
        ][:limit]

    def list_artifacts_by_workspace(self, workspace_id, limit=None, offset=0):
        artifacts = [
            artifact
            for artifact in self.items.values()
            if artifact.workspace_id == workspace_id
        ]
        return artifacts[offset : offset + limit if limit else None]


def write_manifest(root: Path, capability_code: str, composition_graph: dict) -> Path:
    cap_dir = root / "backend" / "app" / "capabilities" / capability_code
    cap_dir.mkdir(parents=True)
    manifest = {
        "id": capability_code,
        "code": capability_code,
        "name": capability_code,
        "version": "0.1.0",
        "composition_graph": composition_graph,
    }
    manifest_path = cap_dir / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump(manifest, sort_keys=False), encoding="utf-8")
    return manifest_path


def valid_contract(backend: str = "capabilities.demo.services.compile:compile_graph"):
    return {
        "enabled": True,
        "contract_version": "1.0.0",
        "accepted_object_roles": ["reference"],
        "node_types": [
            {
                "id": "guidance_card",
                "label": "Guidance Card",
                "input_ports": [
                    {
                        "id": "object",
                        "direction": "input",
                        "data_type": "object_ref",
                        "required": True,
                    }
                ],
                "output_ports": [
                    {
                        "id": "guidance",
                        "direction": "output",
                        "data_type": "guidance",
                    }
                ],
                "payload_schema": {
                    "type": "object",
                    "required": ["intent"],
                    "properties": {"intent": {"type": "string"}},
                    "additionalProperties": True,
                },
            },
            {
                "id": "decision_point",
                "label": "Decision Point",
                "input_ports": [
                    {
                        "id": "guidance",
                        "direction": "input",
                        "data_type": "guidance",
                        "required": True,
                    }
                ],
                "output_ports": [
                    {
                        "id": "guidance",
                        "direction": "output",
                        "data_type": "guidance",
                    }
                ],
                "payload_schema": {"type": "object", "additionalProperties": True},
            },
        ],
        "edge_types": [
            {
                "id": "default",
                "label": "Default",
                "source_data_type": "any",
                "target_data_type": "any",
            }
        ],
        "compile": {"backend": backend, "output_mode": "meeting_command_envelope"},
    }


def graph_nodes():
    return [
        CompositionGraphNode(
            id="ref",
            type="object_reference",
            payload={
                "ref": ObjectRef(
                    uri="mindscape://demo/reference/ref_1",
                    owner_pack="demo",
                    object_kind="reference",
                    object_id="ref_1",
                    workspace_id="ws",
                ).model_dump(mode="json")
            },
        ),
        CompositionGraphNode(
            id="guidance",
            type="guidance_card",
            payload={"intent": "Clarify next choice."},
        ),
        CompositionGraphNode(
            id="decision",
            type="decision_point",
            payload={"question": "Which beat matters most?"},
        ),
    ]


def graph_edges():
    return [
        CompositionGraphEdge(
            id="e1",
            source="ref",
            source_port="object",
            target="guidance",
            target_port="object",
        ),
        CompositionGraphEdge(
            id="e2",
            source="guidance",
            source_port="guidance",
            target="decision",
            target_port="guidance",
        ),
    ]


def test_contract_loader_rejects_pack_declared_object_reference(tmp_path):
    contract = valid_contract()
    contract["node_types"].append(
        {
            "id": "object_reference",
            "label": "Illegal Object Reference",
            "input_ports": [],
            "output_ports": [],
        }
    )
    write_manifest(tmp_path, "demo", contract)

    contracts, diagnostics = load_installed_composition_graph_contracts(
        local_core_root=tmp_path,
        installed_pack_ids=["demo"],
    )

    assert contracts == []
    assert diagnostics[0].code == "invalid_composition_graph_contract"
    assert "object_reference" in diagnostics[0].message


def test_draft_storage_import_export_and_validation(tmp_path):
    write_manifest(tmp_path, "demo", valid_contract())
    store = MemoryArtifactsStore()
    service = CompositionGraphService(
        artifacts_store=store,
        local_core_root=tmp_path,
        installed_pack_ids=["demo"],
    )

    created = service.create_draft(
        "ws",
        CompositionGraphDraftCreateRequest(
            title="Director graph",
            meeting_id="mtg",
            thread_id="thread",
            selected_primary_pack="demo",
            nodes=graph_nodes(),
            edges=graph_edges(),
            viewport=CompositionGraphViewport(x=10, y=20, zoom=0.8),
        ),
    ).draft

    assert store.items[created.id].artifact_type.value == "data"
    assert store.items[created.id].metadata["kind"] == "composition_graph_draft"
    assert service.list_drafts("ws", thread_id="thread").drafts[0].id == created.id

    exported = service.export_draft("ws", created.id)
    assert exported.metadata["export_checksum"]
    imported = service.import_graph(
        "ws",
        CompositionGraphImportRequest(
            graph=CompositionGraphImportExportPayload(
                graph_id="portable",
                selected_primary_pack="demo",
                nodes=exported.nodes,
                edges=exported.edges,
            ),
            thread_id="thread",
        ),
    )
    assert imported.valid is True
    assert imported.draft is not None

    invalid = service.import_graph(
        "ws",
        CompositionGraphImportRequest(
            graph=CompositionGraphImportExportPayload(
                graph_id="bad",
                nodes=[CompositionGraphNode(id="x", type="missing")],
                edges=[],
            )
        ),
    )
    assert invalid.valid is False
    assert invalid.diagnostics[0].code == "unknown_node_type"


@pytest.mark.asyncio
async def test_compile_validates_graph_and_returns_command_envelope(monkeypatch, tmp_path):
    write_manifest(tmp_path, "demo", valid_contract())

    capabilities = types.ModuleType("capabilities")
    demo = types.ModuleType("capabilities.demo")
    services = types.ModuleType("capabilities.demo.services")
    compile_module = types.ModuleType("capabilities.demo.services.compile")

    def compile_graph(**kwargs):
        assert kwargs["selected_primary_pack"] == "demo"
        assert kwargs["composition_graph_ref"]["draft_id"]
        return {
            "command_envelope": {
                "meeting_id": kwargs["meeting_id"],
                "thread_id": kwargs["thread_id"],
                "intent_text": kwargs["command"],
                "requested_action": {
                    "verb": "demo_compile",
                    "pack_code": "demo",
                    "parameters": kwargs["action_parameters"],
                },
            }
        }

    def broken_compile_graph(**_kwargs):
        raise RuntimeError("compile backend unavailable")

    compile_module.compile_graph = compile_graph
    compile_module.broken_compile_graph = broken_compile_graph
    monkeypatch.setitem(sys.modules, "capabilities", capabilities)
    monkeypatch.setitem(sys.modules, "capabilities.demo", demo)
    monkeypatch.setitem(sys.modules, "capabilities.demo.services", services)
    monkeypatch.setitem(sys.modules, "capabilities.demo.services.compile", compile_module)

    store = MemoryArtifactsStore()
    service = CompositionGraphService(
        artifacts_store=store,
        local_core_root=tmp_path,
        installed_pack_ids=["demo"],
    )
    draft = service.create_draft(
        "ws",
        CompositionGraphDraftCreateRequest(
            meeting_id="mtg",
            thread_id="thread",
            selected_primary_pack="demo",
            nodes=graph_nodes(),
            edges=graph_edges(),
        ),
    ).draft

    failed = await service.compile_graph(
        "ws",
        CompositionGraphCompileRequest(
            draft_id=draft.id,
            meeting_id="mtg",
            command="Compile graph",
            selected_primary_pack="missing",
        ),
    )
    assert failed.status == "failed"
    assert failed.diagnostics[0].code == "missing_primary_pack"

    succeeded = await service.compile_graph(
        "ws",
        CompositionGraphCompileRequest(
            draft_id=draft.id,
            meeting_id="mtg",
            thread_id="thread",
            command="Compile graph",
            context_objects=[
                ObjectRoleEntry(
                    role="source",
                    ref=ObjectRef(
                        uri="mindscape://demo/reference/ref_1",
                        owner_pack="demo",
                        object_kind="reference",
                        object_id="ref_1",
                        workspace_id="ws",
                    ),
                )
            ],
            action_parameters={"tone": "specific"},
        ),
    )

    assert succeeded.status == "succeeded"
    assert succeeded.command_envelope is not None
    assert succeeded.command_envelope.requested_action["pack_code"] == "demo"
    assert succeeded.command_envelope.context_objects[0].role == "source"

    store_failure = MemoryArtifactsStore()
    write_manifest(
        tmp_path,
        "broken_demo",
        valid_contract("capabilities.demo.services.compile:broken_compile_graph"),
    )
    failure_service = CompositionGraphService(
        artifacts_store=store_failure,
        local_core_root=tmp_path,
        installed_pack_ids=["broken_demo"],
    )
    failure = await failure_service.compile_graph(
        "ws",
        CompositionGraphCompileRequest(
            meeting_id="mtg",
            command="Compile graph",
            selected_primary_pack="broken_demo",
            nodes=graph_nodes(),
            edges=graph_edges(),
        ),
    )
    assert failure.status == "failed"
    assert failure.diagnostics[0].code == "pack_compile_failed"


def test_required_port_and_cycle_validation(tmp_path):
    write_manifest(tmp_path, "demo", valid_contract())
    service = CompositionGraphService(
        artifacts_store=MemoryArtifactsStore(),
        local_core_root=tmp_path,
        installed_pack_ids=["demo"],
    )

    missing_input = service.validate_graph(
        nodes=graph_nodes(),
        edges=[],
        selected_primary_pack="demo",
        require_primary=True,
    )
    assert {diagnostic.code for diagnostic in missing_input} == {
        "missing_required_input"
    }

    cycle = service.validate_graph(
        nodes=graph_nodes(),
        edges=graph_edges()
        + [
            CompositionGraphEdge(
                id="cycle",
                source="decision",
                source_port="guidance",
                target="guidance",
                target_port="object",
            )
        ],
        selected_primary_pack="demo",
        require_primary=True,
    )
    assert "cycle_detected" in {diagnostic.code for diagnostic in cycle}
