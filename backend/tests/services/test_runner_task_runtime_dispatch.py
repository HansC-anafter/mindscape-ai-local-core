from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner.task_executor import _apply_runtime_binding_to_playbook_task


def _build_task(*, task_type: str = "playbook_execution", capability_code: str = "character_training") -> Task:
    return Task(
        id="task-runtime-dispatch-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        project_id="project-1",
        profile_id="default-user",
        pack_id="character_training_submit",
        task_type=task_type,
        status=TaskStatus.PENDING,
        execution_context={
            "capability_code": capability_code,
            "runtime_affinity": {
                "runtime_id": "runtime-gpu-b",
                "site_key": "gpu-farm",
                "device_id": "gpu-node-b",
                "dispatch_mode": "external_runtime",
            },
        },
        created_at=_utc_now(),
    )


def test_apply_runtime_binding_to_playbook_task_marks_remote_dispatch(monkeypatch):
    task = _build_task()

    monkeypatch.setattr(
        "backend.app.runner.task_executor.resolve_runner_profile_from_env",
        lambda default_max_inflight=1: type(
            "Profile",
            (),
            {
                "profile_code": "gpu_training",
                "display_name": "GPU",
                "dispatch_mode": "external_runtime",
                "accepted_resource_classes": ("compute",),
                "accepted_queue_partitions": ("default_local",),
                "runtime_id": "runtime-gpu-default",
                "max_inflight": 1,
                "enabled": True,
            },
        )(),
    )

    inputs, ctx, binding = _apply_runtime_binding_to_playbook_task(
        task,
        task.execution_context,
        {"workspace_id": task.workspace_id},
        profile_id="default-user",
    )

    assert binding.dispatch_mode == "external_runtime"
    assert inputs["execution_backend"] == "remote"
    assert inputs["remote_job_type"] == "playbook"
    assert inputs["remote_capability_code"] == "character_training"
    assert inputs["runtime_id"] == "runtime-gpu-b"
    assert inputs["site_key"] == "gpu-farm"
    assert inputs["target_device_id"] == "gpu-node-b"
    assert inputs["remote_request_payload"]["runtime_binding"]["runtime_id"] == "runtime-gpu-b"
    assert inputs["remote_request_payload"]["_governance"]["site_key"] == "gpu-farm"
    assert ctx["execution_backend_hint"] == "remote"
    assert ctx["selected_runtime_id"] == "runtime-gpu-b"


def test_apply_runtime_binding_to_playbook_task_does_not_force_remote_for_tool_tasks(monkeypatch):
    task = _build_task(task_type="tool_execution", capability_code="ig")

    monkeypatch.setattr(
        "backend.app.runner.task_executor.resolve_runner_profile_from_env",
        lambda default_max_inflight=1: type(
            "Profile",
            (),
            {
                "profile_code": "gpu_training",
                "display_name": "GPU",
                "dispatch_mode": "external_runtime",
                "accepted_resource_classes": ("compute",),
                "accepted_queue_partitions": ("default_local",),
                "runtime_id": "runtime-gpu-default",
                "max_inflight": 1,
                "enabled": True,
            },
        )(),
    )

    inputs, ctx, _binding = _apply_runtime_binding_to_playbook_task(
        task,
        task.execution_context,
        {"workspace_id": task.workspace_id},
        profile_id="default-user",
    )

    assert "execution_backend" not in inputs
    assert "remote_request_payload" not in inputs
    assert ctx["selected_runtime_id"] == "runtime-gpu-b"
