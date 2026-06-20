import os
import sys
from types import SimpleNamespace

import pytest

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

import backend.app.services.workflow_orchestrator as workflow_module
from backend.app.services.workflow_orchestrator import WorkflowOrchestrator


@pytest.mark.asyncio
async def test_execute_workflow_delegates_to_handoff_helper(monkeypatch) -> None:
    orchestrator = WorkflowOrchestrator()
    handoff_plan = SimpleNamespace(context={"seed": "value"}, steps=[])
    calls = []

    async def fake_helper(
        orchestrator_arg,
        handoff_plan_arg,
        *,
        execution_id=None,
        workspace_id=None,
        profile_id=None,
        project_id=None,
    ):
        calls.append(
            {
                "orchestrator": orchestrator_arg,
                "handoff_plan": handoff_plan_arg,
                "execution_id": execution_id,
                "workspace_id": workspace_id,
                "profile_id": profile_id,
                "project_id": project_id,
            }
        )
        return {"status": "delegated"}

    monkeypatch.setattr(
        workflow_module,
        "workflow_execute_handoff_workflow",
        fake_helper,
    )

    result = await orchestrator.execute_workflow(
        handoff_plan,
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        project_id="project-1",
    )

    assert result == {"status": "delegated"}
    assert calls == [
        {
            "orchestrator": orchestrator,
            "handoff_plan": handoff_plan,
            "execution_id": "exec-1",
            "workspace_id": "ws-1",
            "profile_id": "profile-1",
            "project_id": "project-1",
        }
    ]


@pytest.mark.asyncio
async def test_execute_playbook_steps_delegates_to_helper(monkeypatch) -> None:
    orchestrator = WorkflowOrchestrator()
    playbook_json = SimpleNamespace(playbook_code="demo", steps=[], inputs={})
    calls = []

    async def fake_helper(
        orchestrator_arg,
        playbook_json_arg,
        *,
        playbook_inputs,
        execution_id=None,
        workspace_id=None,
        profile_id=None,
        project_id=None,
    ):
        calls.append(
            {
                "orchestrator": orchestrator_arg,
                "playbook_json": playbook_json_arg,
                "playbook_inputs": playbook_inputs,
                "execution_id": execution_id,
                "workspace_id": workspace_id,
                "profile_id": profile_id,
                "project_id": project_id,
            }
        )
        return {"outputs": {"ok": True}}

    monkeypatch.setattr(
        workflow_module,
        "workflow_execute_playbook_steps",
        fake_helper,
    )

    result = await orchestrator._execute_playbook_steps(
        playbook_json,
        {"input": "value"},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        project_id="project-1",
    )

    assert result == {"outputs": {"ok": True}}
    assert calls[0]["orchestrator"] is orchestrator
    assert calls[0]["playbook_json"] is playbook_json
    assert calls[0]["playbook_inputs"] == {"input": "value"}
    assert calls[0]["execution_id"] == "exec-1"
    assert calls[0]["workspace_id"] == "ws-1"
    assert calls[0]["profile_id"] == "profile-1"
    assert calls[0]["project_id"] == "project-1"


@pytest.mark.asyncio
async def test_execute_single_step_iteration_delegates_to_helper(monkeypatch) -> None:
    orchestrator = WorkflowOrchestrator()
    step = SimpleNamespace(id="step-1")
    playbook_json = SimpleNamespace(playbook_code="demo")
    calls = []

    async def fake_helper(
        orchestrator_arg,
        step_arg,
        playbook_json_arg,
        playbook_inputs_arg,
        step_outputs_arg,
        playbook_input_defs_arg,
        *,
        execution_id=None,
        workspace_id=None,
        profile_id=None,
        project_id=None,
        step_index=0,
    ):
        calls.append(
            (
                orchestrator_arg,
                step_arg,
                playbook_json_arg,
                playbook_inputs_arg,
                step_outputs_arg,
                playbook_input_defs_arg,
                execution_id,
                workspace_id,
                profile_id,
                project_id,
                step_index,
            )
        )
        return {"iteration": "delegated"}

    monkeypatch.setattr(
        workflow_module,
        "workflow_execute_single_step_iteration",
        fake_helper,
    )

    result = await orchestrator._execute_single_step_iteration(
        step,
        playbook_json,
        {"input": "value"},
        {"previous": {"ok": True}},
        {"defs": "value"},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        project_id="project-1",
        step_index=3,
    )

    assert result == {"iteration": "delegated"}
    assert calls == [
        (
            orchestrator,
            step,
            playbook_json,
            {"input": "value"},
            {"previous": {"ok": True}},
            {"defs": "value"},
            "exec-1",
            "ws-1",
            "profile-1",
            "project-1",
            3,
        )
    ]


@pytest.mark.asyncio
async def test_execute_single_step_delegates_to_helper(monkeypatch) -> None:
    orchestrator = WorkflowOrchestrator()
    step = SimpleNamespace(id="step-1", outputs={})
    playbook_json = SimpleNamespace(playbook_code="demo")
    calls = []

    async def fake_helper(
        orchestrator_arg,
        step_arg,
        playbook_json_arg,
        playbook_inputs_arg,
        step_outputs_arg,
        playbook_input_defs_arg,
        *,
        execution_id=None,
        workspace_id=None,
        profile_id=None,
        project_id=None,
        step_index=0,
    ):
        calls.append(
            {
                "orchestrator": orchestrator_arg,
                "step": step_arg,
                "playbook_json": playbook_json_arg,
                "playbook_inputs": playbook_inputs_arg,
                "step_outputs": step_outputs_arg,
                "playbook_input_defs": playbook_input_defs_arg,
                "execution_id": execution_id,
                "workspace_id": workspace_id,
                "profile_id": profile_id,
                "project_id": project_id,
                "step_index": step_index,
            }
        )
        return {"step": "delegated"}

    monkeypatch.setattr(
        workflow_module,
        "workflow_execute_single_step",
        fake_helper,
    )

    result = await orchestrator._execute_single_step(
        step,
        playbook_json,
        {"input": "value"},
        {"previous": {"ok": True}},
        {"defs": "value"},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        project_id="project-1",
        step_index=5,
    )

    assert result == {"step": "delegated"}
    assert calls[0]["orchestrator"] is orchestrator
    assert calls[0]["step"] is step
    assert calls[0]["playbook_json"] is playbook_json
    assert calls[0]["playbook_inputs"] == {"input": "value"}
    assert calls[0]["step_outputs"] == {"previous": {"ok": True}}
    assert calls[0]["playbook_input_defs"] == {"defs": "value"}
    assert calls[0]["execution_id"] == "exec-1"
    assert calls[0]["workspace_id"] == "ws-1"
    assert calls[0]["profile_id"] == "profile-1"
    assert calls[0]["project_id"] == "project-1"
    assert calls[0]["step_index"] == 5
