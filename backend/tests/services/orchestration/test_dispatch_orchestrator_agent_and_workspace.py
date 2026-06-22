"""Agent dispatch and workspace picker tests for DispatchOrchestrator."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from backend.tests.services.orchestration.dispatch_orchestrator_test_support import (
    FakePhaseIR,
    FakeSession,
    FakeTaskIR,
    make_fake_dispatch_orchestrator,
    make_orchestrator,
)


class TestAgentDispatch:
    """Agent-preferring phases should route through WorkspaceAgentExecutor."""

    @pytest.mark.asyncio
    async def test_agent_engine_dispatches_to_workspace_runtime_with_inputs(self):
        session = FakeSession(workspace_id="ws-agent")
        orch = make_orchestrator(
            session=session,
            profile_id="user-1",
            project_id="proj-1",
        )
        phases = [
            FakePhaseIR(
                id="phase_0",
                name="Write persona OS",
                description="Create the persona operating system deliverable",
                preferred_engine="agent:codex_cli",
                input_params={
                    "deliverable_name": "Persona OS",
                    "deliverable_path": "persona_operating_system.md",
                    "user_request": (
                        "Write the persona operating system and save it to "
                        "persona_operating_system.md."
                    ),
                    "context": "Original request: build the persona system",
                },
            )
        ]
        items = [
            {
                "title": "Write persona OS",
                "description": "Create the persona operating system deliverable",
                "engine": "agent:codex_cli",
                "input_params": {
                    "deliverable_name": "Persona OS",
                    "deliverable_path": "persona_operating_system.md",
                    "user_request": (
                        "Write the persona operating system and save it to "
                        "persona_operating_system.md."
                    ),
                    "context": "Original request: build the persona system",
                },
            }
        ]
        workspace = SimpleNamespace(
            id="ws-agent",
            resolved_executor_runtime="codex_cli",
            executor_runtime="codex_cli",
        )
        agent_response = SimpleNamespace(
            success=True,
            output="done",
            error=None,
            execution_id="exec-agent-1",
            trace_id="trace-agent-1",
        )

        with patch(
            "backend.app.services.stores.postgres.workspaces_store.PostgresWorkspacesStore"
        ) as mock_store_cls, patch(
            "backend.app.services.workspace_agent_executor.WorkspaceAgentExecutor"
        ) as mock_executor_cls:
            mock_store_cls.return_value.get_workspace = AsyncMock(return_value=workspace)
            executor = mock_executor_cls.return_value
            executor.check_agent_available = AsyncMock(return_value=True)
            executor.execute = AsyncMock(return_value=agent_response)

            result = await orch.execute(
                task_ir=FakeTaskIR(phases=phases),
                action_items=items,
            )

        assert result["status"] == "ok"
        executor.check_agent_available.assert_awaited_once_with("codex_cli")
        executor.execute.assert_awaited_once()
        call_kwargs = executor.execute.await_args.kwargs
        assert call_kwargs["task"] == (
            "Write the persona operating system and save it to "
            "persona_operating_system.md."
        )
        assert call_kwargs["agent_id"] == "codex_cli"
        assert (
            call_kwargs["context_overrides"]["inputs"]["deliverable_path"]
            == "persona_operating_system.md"
        )
        assert call_kwargs["context_overrides"]["meeting_session_id"] == "session-1"
        assert session.metadata["execution_ids"] == ["exec-agent-1"]


class TestWorkspacePickNormalization:
    """Workspace execution picker should receive deterministic required params."""

    @pytest.mark.asyncio
    async def test_workspace_pick_relevant_execution_hydrates_inputs(self):
        orch = make_fake_dispatch_orchestrator(
            session=FakeSession(workspace_id="ws-e2e"),
            profile_id="user-1",
            project_id="proj-keep-out",
        )
        candidate_task = SimpleNamespace(
            id="task-1",
            execution_id="exec-1",
            pack_id="ig_generate_personas",
            task_type="playbook_execution",
            status=SimpleNamespace(value="completed"),
            project_id="proj-other",
            created_at="2026-04-18T00:00:00+00:00",
            model_dump=lambda mode="json": {
                "id": "task-1",
                "execution_id": "exec-1",
                "pack_id": "ig_generate_personas",
                "status": "completed",
                "created_at": "2026-04-18T00:00:00+00:00",
            },
        )
        phases = [
            FakePhaseIR(
                id="phase_0",
                name="Pick relevant workspace execution",
                description="Find the best prior workspace execution for evidence reuse",
                tool_name="workspace.pick_relevant_execution",
                input_params={},
            )
        ]

        with patch(
            "backend.app.services.orchestration.dispatch_orchestrator_core.planner.TasksStore"
        ) as mock_store:
            mock_store.return_value.list_tasks_by_workspace.return_value = [candidate_task]
            await orch.execute(
                task_ir=FakeTaskIR(phases=phases),
                action_items=[{"title": "Pick relevant workspace execution"}],
            )

        params = phases[0].input_params or {}
        assert params["user_query"] == (
            "Pick relevant workspace execution "
            "Find the best prior workspace execution for evidence reuse"
        )
        assert params["candidates"][0]["execution_id"] == "exec-1"
        assert params["candidates"][0]["playbook_code"] == "ig_generate_personas"
