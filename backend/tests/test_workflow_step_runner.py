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

from backend.app.models.playbook import InteractionMode, PlaybookKind
from backend.app.services.workflow.step_runner import (
    execute_workflow_step,
    merge_workflow_context_into_inputs,
)


def test_merge_workflow_context_into_inputs_preserves_explicit_values() -> None:
    merged = merge_workflow_context_into_inputs(
        playbook_code="demo_step",
        resolved_inputs={"workspace_id": "explicit", "prompt": "hi"},
        workflow_context={"workspace_id": "context", "profile_id": "user-1"},
    )

    assert merged == {
        "workspace_id": "explicit",
        "prompt": "hi",
        "profile_id": "user-1",
    }


@pytest.mark.asyncio
async def test_execute_workflow_step_routes_system_tool_to_playbook_executor() -> None:
    execute_calls = []

    async def execute_playbook_steps(*args):
        execute_calls.append(args)
        return {"status": "completed", "outputs": {"summary": "ok"}}

    result = await execute_workflow_step(
        step=SimpleNamespace(
            playbook_code="demo_step",
            kind=PlaybookKind.SYSTEM_TOOL,
            interaction_mode=[InteractionMode.SILENT],
        ),
        workflow_context={"workspace_id": "ws-1"},
        previous_results={"prepare": {"summary": "ok"}},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="profile-1",
        project_id="proj-1",
        load_playbook_json_fn=lambda playbook_code: {"playbook_code": playbook_code},
        prepare_workflow_step_inputs_fn=lambda step, previous_results, workflow_context: {
            "prompt": "run"
        },
        execute_playbook_steps_fn=execute_playbook_steps,
    )

    assert result["status"] == "completed"
    assert execute_calls[0][1]["workspace_id"] == "ws-1"


@pytest.mark.asyncio
async def test_execute_workflow_step_raises_for_unknown_kind() -> None:
    with pytest.raises(ValueError, match="Unknown playbook kind"):
        await execute_workflow_step(
            step=SimpleNamespace(
                playbook_code="demo_step",
                kind="unknown",
                interaction_mode=[],
            ),
            workflow_context={},
            previous_results={},
            execution_id="exec-1",
            workspace_id="ws-1",
            profile_id=None,
            project_id=None,
            load_playbook_json_fn=lambda playbook_code: {"playbook_code": playbook_code},
            prepare_workflow_step_inputs_fn=lambda step, previous_results, workflow_context: {},
            execute_playbook_steps_fn=_unexpected_execute,
        )


@pytest.mark.asyncio
async def test_execute_workflow_step_raises_when_playbook_missing() -> None:
    with pytest.raises(ValueError, match="playbook.json not found"):
        await execute_workflow_step(
            step=SimpleNamespace(
                playbook_code="missing_playbook",
                kind=PlaybookKind.USER_WORKFLOW,
                interaction_mode=[InteractionMode.CONVERSATIONAL],
            ),
            workflow_context={},
            previous_results={},
            execution_id="exec-1",
            workspace_id="ws-1",
            profile_id=None,
            project_id=None,
            load_playbook_json_fn=lambda playbook_code: None,
            prepare_workflow_step_inputs_fn=lambda step, previous_results, workflow_context: {},
            execute_playbook_steps_fn=_unexpected_execute,
        )


async def _unexpected_execute(*args):
    raise AssertionError("execute_playbook_steps_fn should not be called")
