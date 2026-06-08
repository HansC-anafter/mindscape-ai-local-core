from backend.app.services.model_routing_policy_service import ModelRoutingPolicyService


def test_vision_profile_uses_explicit_host_resource_mlx_env(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNTIME_ADAPTER_ID", "apple_mlx_vlm")
    monkeypatch.setenv("LOCAL_CORE_RUNTIME_ENVIRONMENT_ID", "runtime-35b")
    monkeypatch.setenv("LOCAL_CORE_RUNTIME_ENDPOINT", "http://host.docker.internal:8211")
    monkeypatch.setenv("LOCAL_CORE_HOST_RESOURCE_LANE_ID", "runner:vision_mlx_high")
    monkeypatch.setenv(
        "VLM_WATCHDOG_STATE_FILE",
        "/app/data/runtime/mlx-watchdog/runner_vision_mlx_high.json",
    )
    monkeypatch.setenv(
        "VLM_PROCESS_LOCK_FILE",
        "/app/data/runtime/mlx-watchdog/runner_vision_mlx_high.lock",
    )
    monkeypatch.setenv(
        "MLX_MODEL",
        "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit",
    )
    monkeypatch.setenv("LOCAL_CORE_RUNTIME_MAX_OUTPUT_TOKENS", "512")
    monkeypatch.setenv("LOCAL_CORE_RUNTIME_CONTEXT_BUDGET_TOKENS", "8192")

    route = ModelRoutingPolicyService._resolve_host_resource_env_profile_model(
        profile="vision",
        scope="local",
    )

    assert route.model_name == (
        "froggeric/Qwen3.6-35B-A3B-Uncensored-Heretic-MLX-4bit"
    )
    assert route.provider == "mlx"
    assert route.source == "host_resource_runtime_env.local.vision"
    assert route.metadata["base_url"] == "http://host.docker.internal:8211"
    assert route.metadata["runtime_provider"] == "mlx"
    assert route.metadata["local_max_output_tokens_cap"] == "512"
    assert route.metadata["local_context_budget_tokens"] == "8192"
    assert (
        route.metadata["vlm_watchdog_state_file"]
        == "/app/data/runtime/mlx-watchdog/runner_vision_mlx_high.json"
    )
    assert (
        route.metadata["vlm_process_lock_file"]
        == "/app/data/runtime/mlx-watchdog/runner_vision_mlx_high.lock"
    )


def test_host_resource_mlx_env_is_limited_to_local_vision(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNTIME_ADAPTER_ID", "apple_mlx_vlm")
    monkeypatch.setenv("LOCAL_CORE_RUNTIME_ENDPOINT", "http://host.docker.internal:8211")
    monkeypatch.setenv("MLX_MODEL", "model/vision")

    route = ModelRoutingPolicyService._resolve_host_resource_env_profile_model(
        profile="chat",
        scope="local",
    )

    assert route is None
