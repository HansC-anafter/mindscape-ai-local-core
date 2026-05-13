from __future__ import annotations

from backend.app.models.object_runtime import CompositionGraphDraftCreateRequest
from backend.app.services.object_runtime.composition_graph_service import CompositionGraphService

from composition_graph_service_spec import (
    MemoryArtifactsStore,
    graph_edges,
    graph_nodes,
    valid_contract,
    write_manifest,
)


def test_export_sanitizes_non_portable_graph_payload(tmp_path):
    write_manifest(tmp_path, "demo", valid_contract())
    store = MemoryArtifactsStore()
    service = CompositionGraphService(
        artifacts_store=store,
        local_core_root=tmp_path,
        installed_pack_ids=["demo"],
    )
    nodes = graph_nodes()
    nodes[1].payload["local_path"] = "/Users/example/private.txt"
    nodes[1].payload["safe_value"] = "kept"

    draft = service.create_draft(
        "ws",
        CompositionGraphDraftCreateRequest(
            selected_primary_pack="demo",
            nodes=nodes,
            edges=graph_edges(),
            metadata={
                "runtime_logs": ["raw"],
                "safe_metadata": "kept",
            },
        ),
    ).draft

    exported = service.export_draft("ws", draft.id)
    assert exported.nodes[1].payload["safe_value"] == "kept"
    assert "local_path" not in exported.nodes[1].payload
    assert exported.metadata["safe_metadata"] == "kept"
    assert "runtime_logs" not in exported.metadata
    assert exported.metadata["export_checksum"]
