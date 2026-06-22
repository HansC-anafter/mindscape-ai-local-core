from backend.app.services.runner_topology.profile_registry import RunnerProfile
from backend.app.services.runner_topology.runtime_binding import (
    resolve_runtime_dispatch_target,
)


def _profile(
    *,
    runtime_id: str | None,
    dispatch_mode: str = "docker_local",
) -> RunnerProfile:
    return RunnerProfile(
        profile_code="default_local_browser",
        display_name="Default Local Browser",
        dispatch_mode=dispatch_mode,
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("default_local_browser",),
        runtime_id=runtime_id,
        max_inflight=1,
    )


def test_unresolved_local_runner_runtime_id_stays_docker_local():
    binding = resolve_runtime_dispatch_target(
        _profile(runtime_id="spillover:default_local_browser"),
        {"runtime_affinity": "local"},
        runtime_lookup=lambda runtime_id: None,
    )

    assert binding.dispatch_mode == "docker_local"
    assert binding.runtime_id is None


def test_registered_runtime_environment_can_hydrate_external_runtime_target():
    binding = resolve_runtime_dispatch_target(
        _profile(runtime_id="runtime-vision-mlx"),
        {"runtime_affinity": "local"},
        runtime_lookup=lambda runtime_id: {
            "runtime_id": runtime_id,
            "config_url": "http://host.docker.internal:8212",
            "metadata": {
                "transport": "http",
                "host_resource_slot": {"model_binding_scope": "local"},
            },
        },
    )

    assert binding.dispatch_mode == "external_runtime"
    assert binding.runtime_id == "runtime-vision-mlx"
    assert binding.runtime_url == "http://host.docker.internal:8212"
    assert binding.transport == "http"
    assert binding.binding_scope == "local"


def test_explicit_external_dispatch_keeps_unresolved_runtime_id():
    binding = resolve_runtime_dispatch_target(
        _profile(
            runtime_id="remote-runtime",
            dispatch_mode="external_runtime",
        ),
        {},
        runtime_lookup=lambda runtime_id: None,
    )

    assert binding.dispatch_mode == "external_runtime"
    assert binding.runtime_id == "remote-runtime"
