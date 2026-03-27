from backend.app.services.runner_topology import (
    RunnerProfile,
    resolve_runner_capacity_snapshot,
    resolve_runner_poll_batch_limit,
    runner_profile_has_capacity,
)


def _build_profile(max_inflight: int = 4) -> RunnerProfile:
    return RunnerProfile(
        profile_code="browser_local",
        display_name="Browser",
        dispatch_mode="docker_local",
        accepted_resource_classes=("browser",),
        accepted_queue_partitions=("browser_local",),
        max_inflight=max_inflight,
    )


def test_resolve_runner_poll_batch_limit_defaults_from_profile_capacity():
    profile = _build_profile(max_inflight=6)

    assert resolve_runner_poll_batch_limit(profile) == 60


def test_resolve_runner_poll_batch_limit_never_drops_below_max_inflight():
    profile = _build_profile(max_inflight=6)

    assert resolve_runner_poll_batch_limit(profile, configured_limit=2) == 6


def test_resolve_runner_capacity_snapshot_marks_profile_saturated():
    profile = _build_profile(max_inflight=3)

    snapshot = resolve_runner_capacity_snapshot(profile, inflight=3)

    assert snapshot.max_inflight == 3
    assert snapshot.inflight == 3
    assert snapshot.available_slots == 0
    assert snapshot.saturated is True


def test_runner_profile_has_capacity_uses_snapshot_capacity():
    profile = _build_profile(max_inflight=2)

    assert runner_profile_has_capacity(profile, inflight=1)
    assert not runner_profile_has_capacity(profile, inflight=2)
