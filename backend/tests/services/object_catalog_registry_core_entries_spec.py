import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
BACKEND_ROOT = REPO_ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

import backend.app as backend_app

sys.modules["app"] = backend_app

from app.services.object_catalog_registry import ObjectCatalogRegistry


def test_object_catalog_registry_merges_core_host_resource_entries_without_persisting(
    tmp_path,
):
    registry = ObjectCatalogRegistry(tmp_path)

    payload = registry.read_registry()
    entries = payload["objects"]
    core_entries = [
        entry for entry in entries if entry["owner_pack"] == "local_core"
    ]

    assert {entry["object_kind"] for entry in core_entries} == {
        "host_resource_lane",
        "resource_budget_policy",
        "route_reservation",
        "workspace_resource_allocation",
    }
    assert registry.registry_path.exists() is False

    lane_entry = registry.get_entry("local_core", "host_resource_lane")
    assert lane_entry is not None
    assert lane_entry["indexer_backend"].endswith(":sync_host_resource_lane_index")
    assert [
        affordance["verb"] for affordance in lane_entry["affordances"]
    ] == ["preview_route_intent"]
    assert "worker" not in json.dumps(lane_entry["affordances"])


def test_object_catalog_registry_keeps_core_entries_out_of_pack_registry_file(
    tmp_path,
):
    registry = ObjectCatalogRegistry(tmp_path)
    manifest = {
        "object_exports": [
            {
                "kind": "reference",
                "display_name": "IG Reference",
                "id_field": "reference_id",
            }
        ]
    }

    result = registry.sync_pack_objects("ig", manifest)
    registry_payload = json.loads(result.registry_path.read_text(encoding="utf-8"))

    assert [entry["owner_pack"] for entry in registry_payload["objects"]] == ["ig"]
    assert registry.get_entry("local_core", "host_resource_lane") is not None
