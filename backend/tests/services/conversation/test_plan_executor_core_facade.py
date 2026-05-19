from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.models.workspace import SideEffectLevel
from backend.app.services.conversation import plan_executor as plan_executor_module
from backend.app.services.conversation.plan_executor_core import runtime as runtime_module
from backend.app.services.conversation.plan_executor import PlanExecutor


def _executor():
    return PlanExecutor(
        plan_preparer=Mock(),
        playbook_resolver=Mock(),
        execution_launcher=Mock(),
        error_policy=Mock(),
        plan_builder=Mock(),
        tasks_store=Mock(),
    )


@pytest.mark.asyncio
async def test_plan_executor_facade_delegates_execute_plan(monkeypatch):
    executor = _executor()
    observed = {}

    async def fake_execute_plan(_executor, **kwargs):
        observed["executor"] = _executor
        observed["kwargs"] = kwargs
        return {"executed_tasks": ["ok"], "suggestion_cards": [], "skipped_tasks": []}

    monkeypatch.setattr(plan_executor_module, "execute_plan_helper", fake_execute_plan)

    result = await executor.execute_plan(
        execution_plan=SimpleNamespace(tasks=[]),
        ctx=SimpleNamespace(workspace_id="ws_1"),
        message_id="msg_1",
        files=["file_1"],
        message="Run",
        project_id="project_1",
        event_emitter=Mock(),
        workspace=SimpleNamespace(playbook_auto_execution_config={}),
        prevent_suggestion_creation=True,
        suggestion_creator=Mock(),
    )

    assert result["executed_tasks"] == ["ok"]
    assert observed["executor"] is executor
    assert observed["kwargs"]["message_id"] == "msg_1"
    assert observed["kwargs"]["prevent_suggestion_creation"] is True


@pytest.mark.asyncio
async def test_plan_executor_facade_delegates_private_helpers(monkeypatch):
    executor = _executor()
    calls = {}

    def fake_determine_auto_execute(**kwargs):
        calls["auto"] = kwargs
        return True

    async def fake_execute_readonly_task(_executor, **kwargs):
        calls["readonly"] = (_executor, kwargs)
        return {"execution_id": "exec_1"}

    async def fake_handle_execution_failure(_executor, **kwargs):
        calls["failure"] = (_executor, kwargs)

    async def fake_handle_soft_write_task(_executor, **kwargs):
        calls["soft"] = (_executor, kwargs)
        return {"suggestion": True, "result": {"id": "suggestion_1"}}

    monkeypatch.setattr(
        plan_executor_module,
        "determine_auto_execute_helper",
        fake_determine_auto_execute,
    )
    monkeypatch.setattr(
        plan_executor_module,
        "execute_readonly_task_helper",
        fake_execute_readonly_task,
    )
    monkeypatch.setattr(
        plan_executor_module,
        "handle_execution_failure_helper",
        fake_handle_execution_failure,
    )
    monkeypatch.setattr(
        plan_executor_module,
        "handle_soft_write_task_helper",
        fake_handle_soft_write_task,
    )

    task_plan = SimpleNamespace(pack_id="pack.alpha", auto_execute=False, params={})
    assert (
        executor._determine_auto_execute(
            task_plan=task_plan,
            side_effect_level=SideEffectLevel.READONLY,
            execution_mode="execution",
            execution_priority="medium",
            auto_exec_config={},
        )
        is True
    )
    readonly = await executor._execute_readonly_task(
        task_plan=task_plan,
        ctx=SimpleNamespace(workspace_id="ws_1"),
        message_id="msg_1",
        files=[],
        message="Run",
        project_id=None,
        event_emitter=Mock(),
    )
    await executor._handle_execution_failure(
        task_plan=task_plan,
        ctx=SimpleNamespace(workspace_id="ws_1"),
        message_id="msg_1",
        results={"suggestion_cards": [], "skipped_tasks": []},
        prevent_suggestion_creation=True,
        suggestion_creator=None,
        event_emitter=Mock(),
    )
    soft = await executor._handle_soft_write_task(
        task_plan=task_plan,
        ctx=SimpleNamespace(workspace_id="ws_1"),
        message_id="msg_1",
        files=[],
        message="Run",
        project_id=None,
        event_emitter=Mock(),
        auto_exec_config={},
        execution_priority="medium",
        prevent_suggestion_creation=False,
        suggestion_creator=Mock(),
    )

    assert readonly["execution_id"] == "exec_1"
    assert soft["result"]["id"] == "suggestion_1"
    assert calls["auto"]["execution_mode"] == "execution"
    assert calls["readonly"][0] is executor
    assert calls["failure"][0] is executor
    assert calls["soft"][0] is executor


@pytest.mark.asyncio
async def test_readonly_retry_success_skips_failure_handler(monkeypatch):
    class FakeRecoveryHandler:
        def __init__(self, recovery_policy, max_retries):
            self.recovery_policy = recovery_policy
            self.max_retries = max_retries

        async def handle_error(self, **kwargs):
            return {"action": "retry", "retry_after": 0}

    monkeypatch.setattr(
        "backend.app.services.conversation.recovery_handler.RecoveryHandler",
        FakeRecoveryHandler,
    )

    executor = SimpleNamespace(
        _execute_readonly_task=AsyncMock(
            side_effect=[None, {"execution_id": "exec_retry"}]
        ),
        _handle_execution_failure=AsyncMock(),
    )
    orchestration_state = SimpleNamespace(
        orchestrator=SimpleNamespace(record_step=Mock(), record_error=Mock()),
        remember_primary_execution_id=Mock(),
    )
    runtime_profile = SimpleNamespace(
        recovery_policy=object(),
        stop_conditions=SimpleNamespace(max_retries=1),
    )
    results = {"executed_tasks": [], "suggestion_cards": [], "skipped_tasks": []}

    task_result = await runtime_module._handle_readonly_auto_execute(
        executor=executor,
        task_plan=SimpleNamespace(pack_id="pack.alpha"),
        ctx=SimpleNamespace(workspace_id="ws_1"),
        message_id="msg_1",
        files=[],
        message="Run",
        project_id=None,
        event_emitter=Mock(),
        execution_plan=SimpleNamespace(),
        orchestration_state=orchestration_state,
        runtime_profile=runtime_profile,
        retry_count=0,
        results=results,
        prevent_suggestion_creation=False,
        suggestion_creator=Mock(),
    )

    assert results["executed_tasks"] == [{"execution_id": "exec_retry"}]
    executor._handle_execution_failure.assert_not_called()
    assert task_result == {"retry_count": 1, "error_increment": 1}


@pytest.mark.asyncio
async def test_external_write_failure_returns_error_increment():
    suggestion_creator = SimpleNamespace(create_suggestion_card=AsyncMock(return_value=None))
    executor = SimpleNamespace(error_policy=Mock())
    results = {"executed_tasks": [], "suggestion_cards": [], "skipped_tasks": []}

    increment = await runtime_module._handle_external_write_task(
        executor=executor,
        task_plan=SimpleNamespace(pack_id="pack.external"),
        ctx=SimpleNamespace(workspace_id="ws_1"),
        message_id="msg_1",
        event_emitter=Mock(),
        results=results,
        prevent_suggestion_creation=False,
        suggestion_creator=suggestion_creator,
    )

    assert increment == 1
    assert results["skipped_tasks"] == ["pack.external"]
    executor.error_policy.warn_and_continue.assert_called_once()
