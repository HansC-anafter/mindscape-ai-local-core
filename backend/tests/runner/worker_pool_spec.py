import pytest

from backend.app.runner.worker_pool import build_worker_process_specs


def _base_env(**overrides):
    env = {
        "LOCAL_CORE_RUNNER_ID": "browser-steady",
        "LOCAL_CORE_RUNNER_DISPLAY_NAME": "Browser Steady",
        "LOCAL_CORE_RUNNER_POOL_SIZE": "6",
        "LOCAL_CORE_RUNNER_POST_CLAIM_START_DELAYS_MS": (
            "0,8000,16000,24000,32000,40000"
        ),
        "LOCAL_CORE_RUNNER_POOL_POLL_INTERVALS_MS": "250,350,450,550,650,750",
        "DB_APPLICATION_NAME": "browser-steady",
    }
    env.update(overrides)
    return env


def test_worker_pool_builds_maintenance_owner_and_six_single_slot_workers():
    specs = build_worker_process_specs(_base_env())

    assert [spec.name for spec in specs] == [
        "maintenance",
        "slot-1",
        "slot-2",
        "slot-3",
        "slot-4",
        "slot-5",
        "slot-6",
    ]
    slots = specs[1:]
    assert [spec.env["LOCAL_CORE_RUNNER_MAX_INFLIGHT"] for spec in slots] == [
        "1"
    ] * 6
    assert [
        spec.env["LOCAL_CORE_RUNNER_POST_CLAIM_START_DELAYS_MS"]
        for spec in slots
    ] == ["0", "8000", "16000", "24000", "32000", "40000"]
    assert [spec.env["LOCAL_CORE_RUNNER_POLL_INTERVAL_MS"] for spec in slots] == [
        "250",
        "350",
        "450",
        "550",
        "650",
        "750",
    ]
    assert all(
        spec.env["LOCAL_CORE_RUNNER_STARTUP_RECONCILE_ENABLED"] == "false"
        for spec in slots
    )
    assert specs[0].env["LOCAL_CORE_RUNNER_MAINTENANCE_ONLY"] == "true"


@pytest.mark.parametrize("pool_size", ["0", "8", "bad"])
def test_worker_pool_rejects_invalid_pool_size(pool_size):
    with pytest.raises(ValueError):
        build_worker_process_specs(_base_env(LOCAL_CORE_RUNNER_POOL_SIZE=pool_size))


def test_worker_pool_can_disable_dedicated_maintenance_owner():
    specs = build_worker_process_specs(
        _base_env(LOCAL_CORE_RUNNER_POOL_MAINTENANCE_ENABLED="false")
    )

    assert len(specs) == 6
    assert all(spec.name.startswith("slot-") for spec in specs)
