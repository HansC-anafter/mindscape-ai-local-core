"""Contract, draft, and validation tests for CompositionGraphService."""

from backend.tests.object_runtime.composition_graph_service_test_support import (
    CompositionGraphDraftCreateRequest,
    CompositionGraphEdge,
    CompositionGraphImportExportPayload,
    CompositionGraphImportRequest,
    CompositionGraphNode,
    CompositionGraphService,
    CompositionGraphViewport,
    MemoryArtifactsStore,
    graph_edges,
    graph_nodes,
    load_installed_composition_graph_contracts,
    valid_contract,
    write_manifest,
)


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
