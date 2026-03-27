from __future__ import annotations

from types import SimpleNamespace

from backend.app.routes.core.execution_metadata import (
    resolve_runner_metadata,
    should_route_through_runner,
)


def _build_playbook_run(execution_profile: dict):
    return SimpleNamespace(
        playbook=SimpleNamespace(
            metadata=SimpleNamespace(capability_code="character_training")
        ),
        playbook_json=SimpleNamespace(
            execution_profile=execution_profile,
            concurrency=None,
            lifecycle_hooks=None,
        ),
    )


def test_resolve_runner_metadata_carries_generic_topology_fields():
    playbook_run = _build_playbook_run(
        {
            "resource_class": "compute",
            "queue_partition": "vision_local",
            "runner_profile_hint": "gpu_training",
            "runtime_affinity": {
                "runtime_id": "runtime_gpu_demo",
                "transport": "http",
                "auth_headers": "ignored",
            },
            "runner_timeout_seconds": 7200,
        }
    )

    metadata = resolve_runner_metadata(playbook_run)

    assert metadata == {
        "capability_code": "character_training",
        "runner_timeout_seconds": 7200,
        "resource_class": "compute",
        "queue_partition": "vision_local",
        "queue_shard": "vision_local",
        "runner_profile_hint": "gpu_training",
        "runtime_affinity": {
            "runtime_id": "runtime_gpu_demo",
            "transport": "http",
        },
    }


def test_resolve_runner_metadata_accepts_legacy_queue_shard_as_partition_alias():
    playbook_run = _build_playbook_run({"queue_shard": "ig_browser"})

    metadata = resolve_runner_metadata(playbook_run)

    assert metadata["resource_class"] == "compute"
    assert metadata["queue_partition"] == "browser_local"
    assert metadata["queue_shard"] == "browser_local"


def test_runtime_affinity_requires_runner_routing_even_with_auto_backend():
    playbook_run = _build_playbook_run(
        {
            "resource_class": "compute",
            "runtime_affinity": "runtime_gpu_demo",
        }
    )

    assert should_route_through_runner(
        playbook_run=playbook_run,
        requested_backend="auto",
        env_execution_mode="in_process",
    )
