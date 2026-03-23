from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.services.conversation.plan_executor import PlanExecutor


@pytest.mark.asyncio
async def test_execute_readonly_task_returns_launch_execution_id():
    plan_preparer = Mock()
    plan_preparer.prepare_plan = AsyncMock(
        return_value=SimpleNamespace(
            pack_id="pack.alpha",
            playbook_inputs={"foo": "bar"},
            project_meta={"project": "alpha"},
        )
    )
    playbook_resolver = Mock()
    playbook_resolver.resolve = AsyncMock(
        return_value=SimpleNamespace(code="playbook.alpha")
    )
    execution_launcher = Mock()
    execution_launcher.launch = AsyncMock(return_value={"execution_id": "exec_123"})
    error_policy = Mock()
    tasks_store = Mock()
    tasks_store.get_task_by_execution_id.return_value = None
    event_emitter = Mock()

    executor = PlanExecutor(
        plan_preparer=plan_preparer,
        playbook_resolver=playbook_resolver,
        execution_launcher=execution_launcher,
        error_policy=error_policy,
        plan_builder=Mock(),
        tasks_store=tasks_store,
    )

    result = await executor._execute_readonly_task(
        task_plan=SimpleNamespace(pack_id="pack.alpha", params={"step_id": "step-1"}),
        ctx=SimpleNamespace(workspace_id="ws_123"),
        message_id="msg_123",
        files=[],
        message="run it",
        project_id="proj_123",
        event_emitter=event_emitter,
        execution_plan=SimpleNamespace(
            id="plan_123",
            plan_summary="summary",
            reasoning="reasoning",
            steps=[],
        ),
    )

    assert result == {
        "pack_id": "pack.alpha",
        "playbook_code": "playbook.alpha",
        "execution_id": "exec_123",
    }
    event_emitter.emit_task_created.assert_called_once_with(
        task_id="exec_123",
        pack_id="pack.alpha",
        playbook_code="playbook.alpha",
        status="running",
        task_type="playbook_execution",
        workspace_id="ws_123",
        execution_id="exec_123",
    )
