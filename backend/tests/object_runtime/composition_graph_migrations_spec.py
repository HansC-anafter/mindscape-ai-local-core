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


def test_draft_read_upgrades_older_schema_version(tmp_path):
    write_manifest(tmp_path, "demo", valid_contract())
    store = MemoryArtifactsStore()
    service = CompositionGraphService(
        artifacts_store=store,
        local_core_root=tmp_path,
        installed_pack_ids=["demo"],
    )
    draft = service.create_draft(
        "ws",
        CompositionGraphDraftCreateRequest(
            selected_primary_pack="demo",
            nodes=graph_nodes(),
            edges=graph_edges(),
        ),
    ).draft
    artifact = store.items[draft.id]
    artifact.content["schema_version"] = "composition_graph.v0"

    upgraded = service.get_draft("ws", draft.id).draft

    assert upgraded.schema_version == "composition_graph.v1"
    assert upgraded.migrations[0].from_version == "composition_graph.v0"
    assert upgraded.migrations[0].to_version == "composition_graph.v1"
