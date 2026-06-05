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


def test_worker_target_resolution_prefers_lane_model_over_profile_binding(monkeypatch):
    import backend.app.services.host_resources.worker_target_resolution as resolution

    class _RuntimeStore:
        def get_runtime_environment(self, runtime_environment_id):
            assert runtime_environment_id == "runtime-35b"
            return {
                "id": runtime_environment_id,
                "status": "configured",
                "metadata": {
                    "host_resource_slot": {
                        "adapter_id": "apple_mlx_vlm",
                        "endpoint": {
                            "base_url": "http://localhost:8211",
                            "port": 8211,
                        },
                        "model_binding_scope": "local",
                        "model_binding_profile": "vision",
                    }
                },
            }

    class _SettingsStore:
        def get_profile_model_bindings_for_scope(self, scope):
            assert scope == "local"
            return {"vision": "mlx-community/Qwen3.5-9B-4bit"}

    monkeypatch.setattr(resolution, "RuntimeEnvironmentSlotStore", lambda scope: _RuntimeStore())
    monkeypatch.setattr(resolution, "SystemSettingsStore", lambda: _SettingsStore())
    lane = {
        "lane_id": "runner:vision_mlx_high",
        "resource_flavor": "local.mlx.vision",
        "runner_profile": "vision_mlx_high",
        "queue_shard": "vision_mlx_high",
        "resource_class": "compute",
        "model_profile": {
            "runtime_environment_id": "runtime-35b",
            "port": 8211,
            "model": "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
        },
        "metadata": {},
    }

    result = resolve_worker_target(lane, 1)

    assert result["accepted"] is True
    assert result["model_binding"]["model"] == (
        "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit"
    )
    assert result["model_binding"]["source"] == "lane.model_profile.model"
    assert result["worker_env"]["MLX_MODEL"] == (
        "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit"
    )
    assert result["worker_env"]["MLX_PORT"] == 8211
    assert result["worker_env"]["LOCAL_CORE_RUNNER_DISPATCH_MODE"] == "docker_local"
    assert "LOCAL_CORE_RUNNER_RUNTIME_ID" not in result["worker_env"]


def test_worker_target_resolution_uses_slot_model_before_profile_binding(monkeypatch):
    import backend.app.services.host_resources.worker_target_resolution as resolution

    class _RuntimeStore:
        def get_runtime_environment(self, runtime_environment_id):
            return {
                "id": runtime_environment_id,
                "status": "configured",
                "metadata": {
                    "host_resource_slot": {
                        "adapter_id": "apple_mlx_vlm",
                        "endpoint": {
                            "base_url": "http://localhost:8211",
                            "port": 8211,
                        },
                        "model_binding_scope": "local",
                        "model_binding_profile": "vision",
                        "model": "slot-model/qwen-vision",
                    }
                },
            }

    class _SettingsStore:
        def get_profile_model_bindings_for_scope(self, scope):
            return {"vision": "profile-model/qwen-vision"}

    monkeypatch.setattr(resolution, "RuntimeEnvironmentSlotStore", lambda scope: _RuntimeStore())
    monkeypatch.setattr(resolution, "SystemSettingsStore", lambda: _SettingsStore())
    lane = {
        "lane_id": "runner:vision_mlx_high",
        "resource_flavor": "local.mlx.vision",
        "runner_profile": "vision_mlx_high",
        "queue_shard": "vision_mlx_high",
        "resource_class": "compute",
        "model_profile": {"runtime_environment_id": "runtime-slot-model", "port": 8211},
        "metadata": {},
    }

    result = resolve_worker_target(lane, 1)

    assert result["accepted"] is True
    assert result["model_binding"] == {
        "model": "slot-model/qwen-vision",
        "scope": "local",
        "profile": "vision",
        "source": "host_resource_slot.model",
    }
    assert result["worker_env"]["MLX_MODEL"] == "slot-model/qwen-vision"
    assert result["worker_env"]["LOCAL_CORE_RUNNER_DISPATCH_MODE"] == "docker_local"
    assert "LOCAL_CORE_RUNNER_RUNTIME_ID" not in result["worker_env"]
