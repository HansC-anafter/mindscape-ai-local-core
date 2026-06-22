"""Shared support for composition graph service tests."""

from __future__ import annotations

from pathlib import Path

import yaml

from backend.app.models.object_runtime import (
    CompositionGraphCompileRequest,
    CompositionGraphDraftCreateRequest,
    CompositionGraphEdge,
    CompositionGraphImportExportPayload,
    CompositionGraphImportRequest,
    CompositionGraphNode,
    CompositionGraphRunRequest,
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


def write_node_manifest(
    root: Path,
    capability_code: str,
    composition_graph_nodes: dict,
) -> Path:
    cap_dir = root / "backend" / "app" / "capabilities" / capability_code
    cap_dir.mkdir(parents=True)
    manifest = {
        "id": capability_code,
        "code": capability_code,
        "name": capability_code,
        "version": "0.1.0",
        "composition_graph_nodes": composition_graph_nodes,
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
