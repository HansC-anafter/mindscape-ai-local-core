from backend.app.services.runner_topology import (
    RESOURCE_CLASS_API,
    RESOURCE_CLASS_BROWSER,
    RESOURCE_CLASS_COMPUTE,
    RUNNER_READY_QUEUE_ORDER,
    resolve_runner_profile_from_env,
)


def test_resolve_runner_profile_defaults_to_shared_local(monkeypatch):
    monkeypatch.delenv("LOCAL_CORE_RUNNER_PROFILE", raising=False)
    monkeypatch.delenv("LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS", raising=False)
    monkeypatch.delenv("LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES", raising=False)
    monkeypatch.delenv("LOCAL_CORE_RUNNER_MAX_INFLIGHT", raising=False)

    profile = resolve_runner_profile_from_env(default_max_inflight=3)

    assert profile.profile_code == "shared_local"
    assert profile.accepted_queue_partitions == RUNNER_READY_QUEUE_ORDER
    assert profile.accepted_resource_classes == (
        RESOURCE_CLASS_COMPUTE,
        RESOURCE_CLASS_BROWSER,
        RESOURCE_CLASS_API,
    )
    assert profile.max_inflight == 3


def test_resolve_runner_profile_normalizes_legacy_partition_env(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_PROFILE", "browser_local")
    monkeypatch.setenv(
        "LOCAL_CORE_RUNNER_ACCEPTED_PARTITIONS",
        "ig_browser,browser_local",
    )
    monkeypatch.setenv(
        "LOCAL_CORE_RUNNER_ACCEPTED_RESOURCE_CLASSES",
        "browser",
    )
    monkeypatch.setenv("LOCAL_CORE_RUNNER_MAX_INFLIGHT", "7")

    profile = resolve_runner_profile_from_env(default_max_inflight=2)

    assert profile.profile_code == "browser_local"
    assert profile.accepted_queue_partitions == ("browser_local",)
    assert profile.accepted_resource_classes == (RESOURCE_CLASS_BROWSER,)
    assert profile.max_inflight == 7


def test_resolve_runner_profile_accepts_capability_filter_env(monkeypatch):
    monkeypatch.setenv("LOCAL_CORE_RUNNER_PROFILE", "custom_gpu")
    monkeypatch.setenv("LOCAL_CORE_RUNNER_ACCEPTED_CAPABILITY_CODES", "character_training")

    profile = resolve_runner_profile_from_env(default_max_inflight=1)

    assert profile.profile_code == "custom_gpu"
    assert profile.accepted_capability_codes == ("character_training",)
