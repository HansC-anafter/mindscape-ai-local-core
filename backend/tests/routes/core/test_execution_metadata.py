from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from backend.app.routes.core.execution_metadata import (
    materialize_playbook_input_defaults,
    resolve_runner_metadata,
    seed_playbook_workload_execution_intent,
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


def test_resolve_runner_metadata_treats_local_runtime_affinity_as_local_dispatch():
    playbook_run = _build_playbook_run(
        {
            "resource_class": "browser",
            "queue_shard": "ig_browser",
            "runtime_affinity": "local",
        }
    )

    metadata = resolve_runner_metadata(playbook_run)

    assert metadata["runtime_affinity"] == {"dispatch_mode": "docker_local"}
    assert metadata["queue_partition"] == "browser_local"
    assert metadata["queue_shard"] == "browser_local"


def test_seed_playbook_workload_execution_intent_for_ig_reference_runner_inputs(
    monkeypatch,
):
    monkeypatch.syspath_prepend(
        str(Path(__file__).resolve().parents[3] / "app")
    )
    seeded = seed_playbook_workload_execution_intent(
        playbook_code="ig_analyze_pinned_reference",
        workspace_id="ws-ig-demo",
        inputs={"reference_id": "ref_demo"},
    )

    intent = seeded.get("workload_execution_intent")
    assert seeded["reference_id"] == "ref_demo"
    assert isinstance(intent, dict)
    assert intent["workload_kind"] == "ig.vision_analyze"
    assert intent["workspace_id"] == "ws-ig-demo"
    assert intent["resolution_mode"] == "live_workspace_policy"


def test_seed_playbook_workload_execution_intent_preserves_existing_payload():
    seeded = seed_playbook_workload_execution_intent(
        playbook_code="ig_analyze_pinned_reference",
        workspace_id="ws-ig-demo",
        inputs={
            "workload_execution_intent": {
                "workload_kind": "ig.vision_analyze",
                "workspace_id": "ws-explicit",
            }
        },
    )

    assert seeded["workload_execution_intent"]["workspace_id"] == "ws-explicit"


def test_materialize_playbook_input_defaults_applies_missing_and_blank_values():
    playbook_run = SimpleNamespace(
        playbook=None,
        playbook_json=SimpleNamespace(
            inputs={
                "user_data_dir": SimpleNamespace(
                    default="/app/data/ig-browser-profiles/default"
                ),
                "visit_account_pages": SimpleNamespace(default=True),
            }
        ),
    )

    seeded = materialize_playbook_input_defaults(
        playbook_run=playbook_run,
        inputs={"user_data_dir": "   "},
    )

    assert seeded["user_data_dir"] == "/app/data/ig-browser-profiles/default"
    assert seeded["visit_account_pages"] is True


def test_materialize_playbook_input_defaults_preserves_explicit_values():
    playbook_run = SimpleNamespace(
        playbook=None,
        playbook_json=SimpleNamespace(
            inputs={
                "user_data_dir": SimpleNamespace(
                    default="/app/data/ig-browser-profiles/default"
                ),
                "visit_account_pages": SimpleNamespace(default=True),
            }
        ),
    )

    seeded = materialize_playbook_input_defaults(
        playbook_run=playbook_run,
        inputs={
            "user_data_dir": "/app/data/ig-browser-profiles/custom",
            "visit_account_pages": False,
        },
    )

    assert seeded["user_data_dir"] == "/app/data/ig-browser-profiles/custom"
    assert seeded["visit_account_pages"] is False
