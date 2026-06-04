from backend.app.services.host_resources.runtime_adapter_catalog import list_runtime_adapters
from backend.app.services.host_resources.runtime_environment_slots import (
    normalize_host_resource_slot_metadata,
)
from backend.app.services.host_resources.worker_target_resolution import resolve_worker_target


def test_runtime_adapter_catalog_keeps_protocol_connectors_non_worker():
    adapters = {adapter["adapter_id"]: adapter for adapter in list_runtime_adapters()}

    assert adapters["apple_mlx_vlm"]["worker_capable"] is True
    assert adapters["apple_mlx_vlm"]["model_binding_policy"] == "required"
    assert adapters["a2a_protocol_connector"]["worker_capable"] is False
    assert adapters["a2a_protocol_connector"]["model_binding_policy"] == "forbidden"
    assert adapters["ag_ui_protocol_connector"]["worker_capable"] is False


def test_host_resource_slot_metadata_normalizes_from_nested_payload():
    slot = normalize_host_resource_slot_metadata(
        {
            "host_resource_slot": {
                "adapter_id": "apple_mlx_vlm",
                "endpoint": {"base_url": "http://127.0.0.1:8211", "port": 8211},
            }
        }
    )

    assert slot["resource_kind"] == "host_resource_slot"
    assert slot["adapter_id"] == "apple_mlx_vlm"
    assert slot["model_binding_scope"] == "local"
    assert slot["model_binding_profile"] == "vision"
    assert slot["endpoint"]["base_url"] == "http://127.0.0.1:8211"


def test_worker_target_resolution_rejects_protocol_connector_lane_before_slot_lookup():
    lane = {
        "lane_id": "runner:a2a",
        "resource_flavor": "protocol.a2a",
        "model_profile": {"adapter_id": "a2a_protocol_connector"},
        "metadata": {},
    }

    result = resolve_worker_target(lane, 1)

    assert result["accepted"] is False
    assert result["reason"] == "runtime_adapter_not_worker_capable"
