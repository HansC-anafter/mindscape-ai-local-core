from types import SimpleNamespace
import inspect

import pytest

import backend.app.services.playbook_runner as playbook_runner
from backend.app.services.playbook_runner_core import start_execution


@pytest.mark.asyncio
async def test_start_execution_delegates_to_core_seam(monkeypatch) -> None:
    runner = object.__new__(playbook_runner.PlaybookRunner)
    calls = []

    async def fake_start(runner_arg, **kwargs):
        calls.append((runner_arg, kwargs))
        return {"execution_id": "exec-1"}

    monkeypatch.setattr(playbook_runner, "runner_start_playbook_execution", fake_start)

    result = await playbook_runner.PlaybookRunner.start_playbook_execution(
        runner,
        playbook_code="demo.playbook",
        profile_id="profile-1",
        inputs={"message": "hello"},
        workspace_id="workspace-1",
        project_id="project-1",
        target_language="en",
        variant_id="variant-1",
    )

    assert result == {"execution_id": "exec-1"}
    assert calls == [
        (
            runner,
            {
                "playbook_code": "demo.playbook",
                "profile_id": "profile-1",
                "inputs": {"message": "hello"},
                "workspace_id": "workspace-1",
                "project_id": "project-1",
                "target_language": "en",
                "variant_id": "variant-1",
            },
        )
    ]


@pytest.mark.asyncio
async def test_continue_execution_delegates_to_core_seam(monkeypatch) -> None:
    runner = object.__new__(playbook_runner.PlaybookRunner)
    calls = []

    async def fake_continue(runner_arg, **kwargs):
        calls.append((runner_arg, kwargs))
        return {"execution_id": "exec-2"}

    monkeypatch.setattr(
        playbook_runner,
        "runner_continue_playbook_execution",
        fake_continue,
    )

    result = await playbook_runner.PlaybookRunner.continue_playbook_execution(
        runner,
        execution_id="exec-2",
        user_message="next",
        profile_id="profile-2",
    )

    assert result == {"execution_id": "exec-2"}
    assert calls == [
        (
            runner,
            {
                "execution_id": "exec-2",
                "user_message": "next",
                "profile_id": "profile-2",
            },
        )
    ]


@pytest.mark.asyncio
async def test_reset_current_step_delegates_to_core_seam(monkeypatch) -> None:
    runner = object.__new__(playbook_runner.PlaybookRunner)
    calls = []

    async def fake_reset(runner_arg, **kwargs):
        calls.append((runner_arg, kwargs))
        return {"execution_id": "exec-3", "current_step": 1}

    monkeypatch.setattr(playbook_runner, "runner_reset_current_step", fake_reset)

    result = await playbook_runner.PlaybookRunner.reset_current_step(
        runner,
        execution_id="exec-3",
        profile_id="profile-3",
    )

    assert result == {"execution_id": "exec-3", "current_step": 1}
    assert calls == [
        (
            runner,
            {
                "execution_id": "exec-3",
                "profile_id": "profile-3",
            },
        )
    ]


@pytest.mark.asyncio
async def test_session_state_helpers_remain_on_facade() -> None:
    runner = object.__new__(playbook_runner.PlaybookRunner)
    runner.active_conversations = {
        "exec-complete": SimpleNamespace(extracted_data={"ok": True}),
        "exec-running": SimpleNamespace(extracted_data=None),
    }

    assert await runner.get_playbook_execution_result("exec-complete") == {"ok": True}
    assert await runner.get_playbook_execution_result("exec-running") is None
    assert runner.list_active_executions() == ["exec-complete", "exec-running"]

    runner.cleanup_execution("exec-complete")

    assert runner.list_active_executions() == ["exec-running"]


def test_start_execution_keeps_running_event_before_tool_loop() -> None:
    source = inspect.getsource(start_execution.start_playbook_execution)

    assert source.index("run_playbook_chat_completion") < source.index(
        'new_state="RUNNING"'
    )
    assert source.index('new_state="RUNNING"') < source.index(
        "run_playbook_tool_loop"
    )
