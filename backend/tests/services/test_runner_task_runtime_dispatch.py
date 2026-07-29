from backend.app.models.workspace import Task, TaskStatus, _utc_now
from backend.app.runner.task_executor import _apply_runtime_binding_to_playbook_task
from backend.app.services.runner_topology.runtime_binding import RuntimeBindingTarget


def _build_task(
    *,
    task_type: str = "playbook_execution",
    capability_code: str = "character_training",
    pack_id: str = "character_training_submit",
) -> Task:
    return Task(
        id="task-runtime-dispatch-1",
        workspace_id="ws-1",
        message_id="msg-1",
        execution_id="exec-1",
        project_id="project-1",
        profile_id="default-user",
        pack_id=pack_id,
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
        "backend.app.runner.task_executor_intent.resolve_runner_profile_from_env",
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
        "backend.app.runner.task_executor_intent.resolve_runner_profile_from_env",
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


def test_internal_projection_task_keeps_pointer_payload_on_local_lane(monkeypatch):
    from backend.app.services.knowledge_projection.retrievable.source_admission import (
        INTERNAL_PROJECTION_TOOL,
    )

    task = _build_task(
        task_type="tool_execution",
        capability_code="ig",
        pack_id=INTERNAL_PROJECTION_TOOL,
    )
    task.execution_context["tool_name"] = INTERNAL_PROJECTION_TOOL
    pointer_payload = {
        "contract_version": "knowledge.project-source.v1",
        "internal_task_id": task.id,
    }
    monkeypatch.setattr(
        "backend.app.runner.task_executor_intent.resolve_runner_profile_from_env",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("internal projection must not resolve runtime binding")
        ),
    )

    inputs, ctx, binding = _apply_runtime_binding_to_playbook_task(
        task,
        task.execution_context,
        pointer_payload,
        profile_id="default-user",
    )

    assert binding is None
    assert inputs == pointer_payload
    assert "runtime_binding" not in inputs
    assert "runtime_id" not in inputs
    assert "runtime_binding" not in ctx
    assert "selected_runtime_id" not in ctx


def test_apply_runtime_binding_to_playbook_task_keeps_local_host_runtime_in_process(
    monkeypatch,
):
    task = _build_task(capability_code="decision_assets.synthesize")

    monkeypatch.setattr(
        "backend.app.runner.task_executor_intent.resolve_runner_profile_from_env",
        lambda default_max_inflight=1: type(
            "Profile",
            (),
            {
                "profile_code": "35b_synthesis",
                "display_name": "35B",
                "dispatch_mode": "external_runtime",
                "accepted_resource_classes": ("compute",),
                "accepted_queue_partitions": ("decision_synthesis",),
                "runtime_id": "runtime-35b-synthesis",
                "max_inflight": 1,
                "enabled": True,
            },
        )(),
    )
    monkeypatch.setattr(
        "backend.app.runner.task_executor_intent.resolve_runtime_dispatch_target",
        lambda *_args, **_kwargs: RuntimeBindingTarget(
            dispatch_mode="external_runtime",
            runtime_id="runtime-35b-synthesis",
            runtime_url="http://localhost:8212",
            transport="mlx_vlm_http",
            site_key=None,
            device_id=None,
            binding_scope="local",
            via="task_runtime_affinity+runner_profile+runtime_environment",
        ),
    )

    inputs, ctx, _binding = _apply_runtime_binding_to_playbook_task(
        task,
        task.execution_context,
        {"workspace_id": task.workspace_id},
        profile_id="default-user",
    )

    assert "execution_backend" not in inputs
    assert "remote_request_payload" not in inputs
    assert inputs["runtime_id"] == "runtime-35b-synthesis"
    assert ctx["runtime_binding"]["binding_scope"] == "local"
    assert ctx["selected_runtime_id"] == "runtime-35b-synthesis"
