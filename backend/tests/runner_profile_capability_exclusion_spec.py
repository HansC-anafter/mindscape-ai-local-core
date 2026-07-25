from pathlib import Path

from backend.app.services.runner_topology.profile_registry import (
    RunnerProfile,
    resolve_runner_profile_from_env,
)
from backend.app.services.runner_topology.routing import (
    runner_profile_can_claim_task,
)


ROOT = Path(__file__).resolve().parents[2]


def _task(playbook_code: str) -> dict:
    return {
        "pack_id": playbook_code,
        "queue_shard": "vision_mlx_dev",
        "execution_context": {
            "playbook_code": playbook_code,
            "queue_shard": "vision_mlx_dev",
            "runner_profile_hint": "vision_mlx_dev",
            "resource_class": "compute",
        },
    }


def test_profile_rejected_capability_codes_are_loaded_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LOCAL_CORE_RUNNER_PROFILE", "vision_mlx_dev")
    monkeypatch.setenv(
        "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS",
        "vision_mlx_dev",
    )
    monkeypatch.setenv(
        "LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES",
        "compute",
    )
    monkeypatch.setenv(
        "LOCAL_CORE_RUNNER_REJECTED_CAPABILITY_CODES",
        "ig_analyze_pinned_reference",
    )

    profile = resolve_runner_profile_from_env()

    assert profile.rejected_capability_codes == (
        "ig_analyze_pinned_reference",
    )


def test_rejected_playbook_cannot_be_claimed_but_other_playbook_is_preserved() -> None:
    profile = RunnerProfile(
        profile_code="vision_mlx_dev",
        display_name="Vision MLX Dev",
        dispatch_mode="docker_local",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=("vision_mlx_dev",),
        rejected_capability_codes=("ig_analyze_pinned_reference",),
        max_inflight=1,
    )

    assert not runner_profile_can_claim_task(
        profile,
        _task("ig_analyze_pinned_reference"),
    )
    assert runner_profile_can_claim_task(
        profile,
        _task("decision_assets_synthesize"),
    )


def test_formal_vision_runner_default_is_single_inflight() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    formal_runner = compose.split("  runner-vision:", 1)[1].split(
        "  runner-vision-mlx-dev:",
        1,
    )[0]

    assert (
        "LOCAL_CORE_RUNNER_MAX_INFLIGHT: "
        "${LOCAL_CORE_RUNNER_VISION_MAX_INFLIGHT:-1}"
    ) in formal_runner
    assert "LOCAL_CORE_RUNNER_VISION_MAX_INFLIGHT:-3" not in formal_runner
