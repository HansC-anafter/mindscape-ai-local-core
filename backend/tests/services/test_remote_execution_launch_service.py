import pytest

from backend.app.services.remote_execution_launch_service import (
    RemoteExecutionLaunchService,
)


class _FakeConnector:
    def __init__(self):
        self.is_connected = True
        self.calls = []

    async def start_remote_execution(self, **kwargs):
        self.calls.append(kwargs)
        return {"state": "pending", "id": "cloud-exec-1"}


class _FakeTask:
    def __init__(self):
        self.id = "task-1"
        self.execution_context = {}


class _FakeTasksStore:
    def __init__(self, task):
        self.task = task
        self.updates = []
        self.status_updates = []

    def update_task(self, task_id, **kwargs):
        self.updates.append((task_id, kwargs))
        if "execution_context" in kwargs:
            self.task.execution_context = kwargs["execution_context"]

    def update_task_status(self, task_id, status, **kwargs):
        self.status_updates.append((task_id, status, kwargs))


def test_resolve_dispatch_target_prefers_runtime_binding_metadata():
    service = RemoteExecutionLaunchService(connector=None)

    target = service._resolve_dispatch_target(
        normalized_inputs={
            "runtime_binding": {
                "runtime_id": "runtime-gpu-b",
                "site_key": "gpu-farm",
                "device_id": "gpu-node-b",
                "dispatch_mode": "external_runtime",
            }
        },
        request_payload={
            "inputs": {"runtime_id": "ignored-runtime"},
            "_governance": {"site_key": "ignored-site"},
        },
    )

    assert target == {
        "runtime_id": "runtime-gpu-b",
        "site_key": "gpu-farm",
        "target_device_id": "gpu-node-b",
        "runtime_binding": {
            "dispatch_mode": "external_runtime",
            "runtime_id": "runtime-gpu-b",
            "site_key": "gpu-farm",
            "device_id": "gpu-node-b",
        },
    }


@pytest.mark.asyncio
async def test_dispatch_passes_runtime_binding_target_to_connector(monkeypatch):
    connector = _FakeConnector()
    service = RemoteExecutionLaunchService(connector=connector)
    task = _FakeTask()
    tasks_store = _FakeTasksStore(task)

    monkeypatch.setattr(
        service,
        "_ensure_remote_execution_shell",
        lambda **kwargs: (tasks_store, task),
    )

    result = await service.dispatch(
        playbook_code="character_training_submit",
        inputs={
            "workspace_id": "ws-1",
            "runtime_binding": {
                "runtime_id": "runtime-gpu-b",
                "site_key": "gpu-farm",
                "device_id": "gpu-node-b",
                "dispatch_mode": "external_runtime",
            },
        },
        workspace_id="ws-1",
        profile_id="default-user",
        remote_job_type="playbook",
        remote_request_payload={"inputs": {}},
        capability_code="character_training",
    )

    assert connector.calls[0]["site_key"] == "gpu-farm"
    assert connector.calls[0]["target_device_id"] == "gpu-node-b"
    assert task.execution_context["remote_execution"]["runtime_binding"]["runtime_id"] == "runtime-gpu-b"
    assert task.execution_context["remote_execution"]["runtime_id"] == "runtime-gpu-b"
    assert result["runtime_id"] == "runtime-gpu-b"
