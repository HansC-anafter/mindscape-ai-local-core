import os
import sys

_repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if _repo_root not in sys.path:
    sys.path.insert(0, _repo_root)
_backend_root = os.path.join(_repo_root, "backend")
if _backend_root not in sys.path:
    sys.path.insert(0, _backend_root)

from types import SimpleNamespace

import pytest

from backend.app.services.workflow.step_dispatch import (
    execute_playbook_slot,
    resolve_tool_slot_to_tool_id,
)


@pytest.mark.asyncio
async def test_resolve_tool_slot_to_tool_id_uses_slot_resolver(monkeypatch) -> None:
    calls = []

    class StubResolver:
        async def resolve(self, *, slot, workspace_id, project_id):
            calls.append((slot, workspace_id, project_id))
            return "core_llm.multimodal_analyze"

    monkeypatch.setattr(
        "backend.app.services.workflow.step_dispatch.get_tool_slot_resolver",
        lambda store=None: StubResolver(),
    )

    step = SimpleNamespace(tool_slot="core_llm.vision")
    tool_id = await resolve_tool_slot_to_tool_id(
        step=step,
        store=object(),
        workspace_id="ws-1",
        project_id="proj-1",
    )

    assert tool_id == "core_llm.multimodal_analyze"
    assert calls == [("core_llm.vision", "ws-1", "proj-1")]


@pytest.mark.asyncio
async def test_execute_playbook_slot_requires_runtime_flag(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_PLAYBOOK_SLOT_RUNTIME", "false")
    step = SimpleNamespace(
        id="dispatch_sub",
        playbook_slot="sub_playbook",
        outputs={"summary": "report"},
    )

    with pytest.raises(ValueError, match="runtime dispatch is not enabled"):
        await execute_playbook_slot(
            step=step,
            current_depth=0,
            resolved_inputs={},
            execution_id="exec-1",
            workspace_id="ws-1",
            profile_id="user-1",
            project_id="proj-1",
            load_playbook_json_fn=lambda code: {"playbook_code": code},
            execute_playbook_steps_fn=_unexpected_execute,
        )


@pytest.mark.asyncio
async def test_execute_playbook_slot_maps_sub_playbook_outputs(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_PLAYBOOK_SLOT_RUNTIME", "true")
    calls = []
    step = SimpleNamespace(
        id="dispatch_sub",
        playbook_slot="sub_playbook",
        outputs={"summary": "report", "grade": "score"},
    )

    async def execute_steps(*args, **kwargs):
        calls.append((args, kwargs))
        return {"report": "ok", "score": 42}

    result = await execute_playbook_slot(
        step=step,
        current_depth=0,
        resolved_inputs={"x": 1},
        execution_id="exec-1",
        workspace_id="ws-1",
        profile_id="user-1",
        project_id="proj-1",
        load_playbook_json_fn=lambda code: {"playbook_code": code},
        execute_playbook_steps_fn=execute_steps,
    )

    assert result == {"summary": "ok", "grade": 42}
    assert calls


async def _unexpected_execute(*args, **kwargs):
    raise AssertionError("execute_playbook_steps_fn should not be called")
