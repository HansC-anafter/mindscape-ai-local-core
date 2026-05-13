from __future__ import annotations

from backend.app.services.object_runtime.composition_graph_service import (
    build_core_object_reference_node_type,
    load_installed_composition_graph_contracts,
)

from composition_graph_service_spec import valid_contract, write_manifest


def test_contract_loader_filters_installed_packs_and_keeps_object_reference_core_owned(tmp_path):
    write_manifest(tmp_path, "installed_demo", valid_contract())
    write_manifest(tmp_path, "not_installed_demo", valid_contract())

    contracts, diagnostics = load_installed_composition_graph_contracts(
        local_core_root=tmp_path,
        installed_pack_ids=["installed_demo"],
    )

    assert diagnostics == []
    assert [contract.capability_code for contract in contracts] == ["installed_demo"]
    assert build_core_object_reference_node_type().id == "object_reference"
    assert all(node_type.id != "object_reference" for contract in contracts for node_type in contract.node_types)
