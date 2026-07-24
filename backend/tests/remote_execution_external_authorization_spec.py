from types import SimpleNamespace

import pytest

from backend.app.services.remote_execution_launch_service import (
    RemoteExecutionLaunchService,
)


class FakeConnector:
    is_connected = True

    def __init__(self) -> None:
        self.calls = []

    async def start_remote_execution(self, **kwargs):
        self.calls.append(kwargs)
        return {"id": kwargs["execution_id"], "state": "pending"}


class FakeStore:
    def update_task(self, *args, **kwargs):
        return None


class RecordingLaunchService(RemoteExecutionLaunchService):
    def __init__(self, *, connector):
        super().__init__(connector=connector)
        self.shell_inputs = None

    def _ensure_remote_execution_shell(self, **kwargs):
        self.shell_inputs = kwargs["inputs"]
        task = SimpleNamespace(id=kwargs["execution_id"], execution_context={})
        return FakeStore(), task


@pytest.mark.asyncio
async def test_external_provider_credential_is_transient_not_task_input():
    connector = FakeConnector()
    service = RecordingLaunchService(connector=connector)
    authorization = {
        "decision_id": "decision-one",
        "provider": {
            "access_token": "one-use-secret",
            "token_id": "token-one",
        },
    }

    await service.dispatch(
        playbook_code="ig.ig_query_references",
        inputs={"execution_admission_snapshot": {"snapshot_hash": "a" * 64}},
        workspace_id="workspace-one",
        profile_id="owner",
        execution_id="execution-one",
        trace_id="trace-one",
        remote_job_type="tool",
        external_authorization_context=authorization,
    )

    assert "one-use-secret" not in str(service.shell_inputs)
    payload = connector.calls[0]["request_payload"]
    assert payload["_external_execution_authorization"] == authorization
