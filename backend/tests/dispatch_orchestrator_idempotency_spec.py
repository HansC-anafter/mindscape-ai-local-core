from types import SimpleNamespace

import pytest

from backend.app.models.task_ir import PhaseIR
from backend.app.services.orchestration.dispatch_orchestrator import DispatchOrchestrator


class _UnavailableRegistry:
    def register_attempt(self, **kwargs):
        return None


class _DuplicateRegistry:
    def register_attempt(self, **kwargs):
        return False


class _Launcher:
    def __init__(self):
        self.calls = []

    async def launch(self, **kwargs):
        self.calls.append(kwargs)
        return {"execution_id": "exec_phase_1"}


@pytest.mark.asyncio
async def test_dispatch_orchestrator_fails_open_when_idempotency_registry_unavailable():
    launcher = _Launcher()
    orchestrator = DispatchOrchestrator(
        execution_launcher=launcher,
        session=SimpleNamespace(
            id="meeting_1",
            thread_id="thread_1",
            workspace_id="ws_demo",
            metadata={},
        ),
        profile_id="profile_demo",
        project_id="project_demo",
        handoff_registry_store=_UnavailableRegistry(),
    )

    result = await orchestrator._dispatch_phase(
        PhaseIR(
            id="phase_1",
            name="Generate output",
            preferred_engine="playbook:generic_output_playbook",
        ),
        {"description": "Generate output", "input_params": {}},
        "task_demo",
    )

    assert result["status"] == "completed"
    assert result["result"]["execution_id"] == "exec_phase_1"
    assert len(launcher.calls) == 1


@pytest.mark.asyncio
async def test_dispatch_orchestrator_blocks_explicit_duplicate_idempotency_key():
    launcher = _Launcher()
    orchestrator = DispatchOrchestrator(
        execution_launcher=launcher,
        session=SimpleNamespace(
            id="meeting_1",
            thread_id="thread_1",
            workspace_id="ws_demo",
            metadata={},
        ),
        profile_id="profile_demo",
        project_id="project_demo",
        handoff_registry_store=_DuplicateRegistry(),
    )

    result = await orchestrator._dispatch_phase(
        PhaseIR(
            id="phase_1",
            name="Generate output",
            preferred_engine="playbook:generic_output_playbook",
        ),
        {"description": "Generate output", "input_params": {}},
        "task_demo",
    )

    assert result["status"] == "skipped"
    assert result["reason"] == "idempotency_conflict"
    assert result["dispatch_attempt_reason"]["attempt_status"] == "skipped"
    assert launcher.calls == []
