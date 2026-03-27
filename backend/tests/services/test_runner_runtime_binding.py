from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.services.runner_topology import (
    RunnerProfile,
    resolve_runtime_binding,
    resolve_runtime_dispatch_target,
    resolve_task_runtime_affinity,
)


def _build_task(runtime_affinity=None) -> Task:
    return Task(
        id="task-runtime-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        pack_id="character_training_submit",
        task_type="playbook_execution",
        status=TaskStatus.PENDING,
        queue_shard="default_local",
        execution_context={"runtime_affinity": runtime_affinity} if runtime_affinity is not None else {},
        created_at=_utc_now(),
    )


def test_resolve_task_runtime_affinity_normalizes_string_runtime_id():
    task = _build_task(runtime_affinity=" runtime-gpu-1 ")

    affinity = resolve_task_runtime_affinity(task)

    assert affinity == {"runtime_id": "runtime-gpu-1"}


def test_resolve_runtime_binding_prefers_task_runtime_affinity_over_profile_default():
    profile = RunnerProfile(
        profile_code="gpu_training",
        display_name="GPU Training",
        dispatch_mode="external_runtime",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=("default_local",),
        runtime_id="runtime-gpu-default",
    )
    task = _build_task(
        runtime_affinity={
            "runtime_id": "runtime-gpu-b",
            "runtime_url": "https://gpu-b.internal",
            "transport": "http",
            "dispatch_mode": "external_runtime",
            "device_id": "gpu-node-b",
            "auth_headers": "ignored",
        }
    )

    binding = resolve_runtime_binding(profile, task)

    assert binding.runtime_id == "runtime-gpu-b"
    assert binding.dispatch_mode == "external_runtime"
    assert binding.runtime_url == "https://gpu-b.internal"
    assert binding.transport == "http"
    assert binding.device_id == "gpu-node-b"
    assert binding.site_key is None
    assert binding.via == "task_runtime_affinity+runner_profile"


def test_resolve_runtime_binding_falls_back_to_profile_runtime_id():
    profile = RunnerProfile(
        profile_code="gpu_training",
        display_name="GPU Training",
        dispatch_mode="external_runtime",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=("default_local",),
        runtime_id="runtime-gpu-default",
    )

    binding = resolve_runtime_binding(profile, _build_task())

    assert binding.runtime_id == "runtime-gpu-default"
    assert binding.dispatch_mode == "external_runtime"
    assert binding.via == "runner_profile"


def test_resolve_runtime_binding_keeps_local_profile_without_runtime():
    profile = RunnerProfile(
        profile_code="default_local",
        display_name="Default",
        dispatch_mode="docker_local",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=("default_local",),
    )

    binding = resolve_runtime_binding(profile, _build_task())

    assert binding.runtime_id is None
    assert binding.dispatch_mode == "docker_local"
    assert binding.via == "none"


def test_resolve_runtime_dispatch_target_infers_external_runtime_for_runtime_id():
    profile = RunnerProfile(
        profile_code="shared_local",
        display_name="Shared",
        dispatch_mode="docker_local",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=("default_local",),
    )
    task = _build_task(runtime_affinity="runtime-gpu-b")

    binding = resolve_runtime_dispatch_target(profile, task)

    assert binding.runtime_id == "runtime-gpu-b"
    assert binding.dispatch_mode == "external_runtime"
    assert binding.via == "task_runtime_affinity+runner_profile"


def test_resolve_runtime_dispatch_target_hydrates_runtime_environment_metadata():
    profile = RunnerProfile(
        profile_code="gpu_training",
        display_name="GPU Training",
        dispatch_mode="external_runtime",
        accepted_resource_classes=("compute",),
        accepted_queue_partitions=("default_local",),
        runtime_id="runtime-gpu-default",
    )

    binding = resolve_runtime_dispatch_target(
        profile,
        _build_task(),
        runtime_lookup=lambda runtime_id: {
            "runtime_id": runtime_id,
            "config_url": "https://gpu-b.internal",
            "metadata": {
                "site_key": "gpu-farm",
                "target_device_id": "gpu-node-b",
                "transport": "http",
            },
        },
    )

    assert binding.runtime_id == "runtime-gpu-default"
    assert binding.dispatch_mode == "external_runtime"
    assert binding.runtime_url == "https://gpu-b.internal"
    assert binding.site_key == "gpu-farm"
    assert binding.device_id == "gpu-node-b"
    assert binding.transport == "http"
    assert binding.via == "runner_profile+runtime_environment"
