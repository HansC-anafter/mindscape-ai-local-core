from types import SimpleNamespace

import pytest

from backend.app.capabilities.core_llm.services import multimodal


def test_vision_route_resolves_from_registry_profile_route(monkeypatch):
    class _FakePolicy:
        def resolve_profile_model(self, *, profile, scope, model_type):
            assert profile == "vision"
            assert scope == "local"
            assert str(model_type.value) == "multimodal"
            return SimpleNamespace(
                model_name="qwen-vision-local",
                provider="mlx",
                metadata={"base_url": "http://127.0.0.1:8210"},
                source="system_settings.profile_model_bindings.local.vision",
            )

    monkeypatch.setattr(
        "backend.app.services.model_routing_policy_service.ModelRoutingPolicyService",
        _FakePolicy,
    )

    model_name, provider, metadata = multimodal._resolve_vision_route()

    assert model_name == "qwen-vision-local"
    assert provider == "mlx"
    assert metadata["base_url"] == "http://127.0.0.1:8210"


def test_multimodal_base_url_requires_selected_registry_model_metadata():
    with pytest.raises(ValueError, match="metadata.base_url"):
        multimodal._resolve_multimodal_base_url({})


def test_huggingface_mlx_model_routes_to_mlx_runtime(monkeypatch):
    class _FakePolicy:
        def resolve_profile_model(self, *, profile, scope, model_type):
            return SimpleNamespace(
                model_name="mlx-community/Qwen2.5-VL",
                provider="huggingface",
                metadata={
                    "hf_format": "MLX",
                    "base_url": "http://127.0.0.1:8210",
                },
                source="system_settings.profile_model_bindings.local.vision",
            )

    monkeypatch.setattr(
        "backend.app.services.model_routing_policy_service.ModelRoutingPolicyService",
        _FakePolicy,
    )

    model_name, provider, metadata = multimodal._resolve_vision_route()

    assert model_name == "mlx-community/Qwen2.5-VL"
    assert provider == "mlx"
    assert metadata["base_url"] == "http://127.0.0.1:8210"


def test_multimodal_base_url_accepts_registry_endpoint_alias():
    assert (
        multimodal._resolve_multimodal_base_url(
            {"endpoint_url": "http://127.0.0.1:8210/"}
        )
        == "http://127.0.0.1:8210"
    )


def test_multimodal_watchdog_state_file_defaults_to_legacy_shared_path(monkeypatch):
    monkeypatch.delenv("LOCAL_CORE_HOST_RESOURCE_LANE_ID", raising=False)
    monkeypatch.delenv("LOCAL_CORE_RUNNER_PROFILE", raising=False)
    monkeypatch.delenv("VLM_WATCHDOG_STATE_FILE", raising=False)

    assert (
        str(multimodal._watchdog_state_file({}))
        == "/app/data/runtime/mlx-watchdog/inflight_request.json"
    )


def test_multimodal_watchdog_state_file_uses_host_resource_lane_metadata(monkeypatch):
    monkeypatch.delenv("VLM_WATCHDOG_STATE_FILE", raising=False)

    assert (
        str(
            multimodal._watchdog_state_file(
                {"host_resource_lane_id": "runner:35b_synthesis"}
            )
        )
        == "/app/data/runtime/mlx-watchdog/runner_35b_synthesis.json"
    )
    assert (
        str(
            multimodal._mlx_process_lock_file(
                {"host_resource_lane_id": "runner:35b_synthesis"}
            )
        )
        == "/app/data/runtime/mlx-watchdog/runner_35b_synthesis.lock"
    )


def test_multimodal_watchdog_state_file_prefers_route_metadata_path(monkeypatch):
    monkeypatch.delenv("VLM_WATCHDOG_STATE_FILE", raising=False)

    assert (
        str(
            multimodal._watchdog_state_file(
                {"vlm_watchdog_state_file": "/tmp/custom-lane.json"}
            )
        )
        == "/tmp/custom-lane.json"
    )


def test_multimodal_route_has_no_non_registry_selection_paths():
    source = multimodal.__loader__.get_source(multimodal.__name__)

    forbidden = [
        "_model_override",
        "CapabilityProfileResolver",
        "multimodal_model",
        "Auto-discover",
        "Auto-discovered",
        "Hardcoded fallback",
        "_guess_provider",
        "VISION_MODEL_BASE_URL",
        "VLM_BASE_URL",
        "MLX_SERVER_HOST",
        "host.docker.internal:8210",
        "trying settings fallback",
        "legacy fallback",
        "huggingface_base_url",
        "ModelConfigStore",
        "get_model_by_name",
    ]
    for marker in forbidden:
        assert marker not in source
