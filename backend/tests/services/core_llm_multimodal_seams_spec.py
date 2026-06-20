import inspect

from backend.app.capabilities.core_llm.services import (
    multimodal,
    multimodal_cloud,
    multimodal_huggingface,
    multimodal_mlx,
    multimodal_routing,
)


def test_multimodal_facade_reexports_moved_helpers():
    assert multimodal._route_mlx_server is multimodal_mlx.route_mlx_server
    assert multimodal._route_huggingface is multimodal_huggingface.route_huggingface
    assert multimodal._load_hf_vision_tool is multimodal_huggingface.load_hf_vision_tool
    assert multimodal.check_hf_vision_health is multimodal_huggingface.check_hf_vision_health
    assert multimodal._hf_vision_cache is multimodal_huggingface._hf_vision_cache
    assert multimodal._route_cloud_llm is multimodal_cloud.route_cloud_llm
    assert multimodal._resolve_vision_route is multimodal_routing.resolve_vision_route
    assert (
        multimodal._resolve_multimodal_base_url
        is multimodal_routing.resolve_multimodal_base_url
    )


def test_mlx_route_uses_facade_for_resource_monkeypatch_points():
    source = inspect.getsource(multimodal_mlx.route_mlx_server)

    required_markers = [
        "facade._MLX_SEMAPHORE",
        "facade._VlmProcessFileLock",
        "facade._build_mlx_http_timeout",
        "facade._watchdog_state_file",
        "facade._mlx_process_lock_file",
        "facade._write_watchdog_state",
        "facade._watchdog_heartbeat",
        "facade._preserve_watchdog_state_for_client_timeout",
        "facade._clear_watchdog_state",
        "facade._resolve_multimodal_base_url",
    ]
    for marker in required_markers:
        assert marker in source


def test_multimodal_helpers_do_not_add_runtime_entrypoints_or_legacy_routing():
    helper_sources = "\n".join(
        inspect.getsource(module)
        for module in (
            multimodal_cloud,
            multimodal_huggingface,
            multimodal_mlx,
            multimodal_routing,
        )
    )
    sources = "\n".join(
        inspect.getsource(module)
        for module in (
            multimodal,
            multimodal_cloud,
            multimodal_huggingface,
            multimodal_mlx,
            multimodal_routing,
        )
    )

    forbidden_markers = [
        "APIRouter",
        "include_router",
        "PgBouncer",
        "setInterval",
        "setTimeout",
        "VLM_BASE_URL",
        "MLX_SERVER_HOST",
        "host.docker.internal:8210",
        "ModelConfigStore",
        "CapabilityProfileResolver",
        "Hardcoded fallback",
        "Auto-discover",
        "Auto-discovered",
    ]
    for marker in forbidden_markers:
        assert marker not in sources
    assert "_MLX_SEMAPHORE =" not in helper_sources
