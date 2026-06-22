"""Playbook routing tests for DispatchOrchestrator."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.tests.services.orchestration.dispatch_orchestrator_test_support import (
    DispatchOrchestrator,
    FakePhaseIR,
    FakeSession,
    FakeTaskIR,
    make_orchestrator,
)


class TestPlaybookCodeExtraction:
    """Engine string -> playbook code."""

    def test_extract_playbook_code(self):
        assert (
            DispatchOrchestrator._extract_playbook_code("playbook:generic") == "generic"
        )
        assert (
            DispatchOrchestrator._extract_playbook_code("playbook:deploy") == "deploy"
        )
        assert DispatchOrchestrator._extract_playbook_code(None) is None
        assert DispatchOrchestrator._extract_playbook_code("mcp:server") is None


class TestPlaybookAliasRescue:
    """Tool-like phases that name playbooks should route to playbooks."""

    @pytest.mark.asyncio
    async def test_exact_playbook_code_in_tool_name_reroutes_to_playbook(self):
        launcher = SimpleNamespace(
            launch=AsyncMock(return_value={"execution_id": "exec-1"})
        )
        orch = make_orchestrator(
            execution_launcher=launcher,
            session=FakeSession(),
            profile_id="user-1",
            available_playbooks_cache="- page_outline: Page Outline\n",
        )
        phases = [
            FakePhaseIR(
                id="phase_0",
                name="Build outline",
                preferred_engine="tool:page_outline",
                tool_name="page_outline",
                input_params={},
            )
        ]
        items = [{"title": "Build outline", "tool_name": "page_outline"}]

        result = await orch.execute(task_ir=FakeTaskIR(phases=phases), action_items=items)

        assert result["status"] == "ok"
        launcher.launch.assert_awaited_once()
        assert launcher.launch.await_args.kwargs["playbook_code"] == "page_outline"
        assert phases[0].tool_name is None
        assert phases[0].preferred_engine == "playbook:page_outline"
        assert items[0]["playbook_code"] == "page_outline"
        assert items[0]["tool_name"] is None

    @pytest.mark.asyncio
    async def test_exact_playbook_code_in_tool_name_reroutes_without_cache(self):
        launcher = SimpleNamespace(
            launch=AsyncMock(return_value={"execution_id": "exec-1b"})
        )
        orch = make_orchestrator(
            execution_launcher=launcher,
            session=FakeSession(),
            profile_id="user-1",
            available_playbooks_cache="",
        )
        phases = [
            FakePhaseIR(
                id="phase_0",
                name="Build outline",
                preferred_engine="tool:page_outline",
                tool_name="page_outline",
                input_params={},
            )
        ]
        items = [{"title": "Build outline", "tool_name": "page_outline"}]

        result = await orch.execute(task_ir=FakeTaskIR(phases=phases), action_items=items)

        assert result["status"] == "ok"
        launcher.launch.assert_awaited_once()
        assert launcher.launch.await_args.kwargs["playbook_code"] == "page_outline"
        assert phases[0].tool_name is None
        assert phases[0].preferred_engine == "playbook:page_outline"
        assert items[0]["playbook_code"] == "page_outline"
        assert items[0]["tool_name"] is None

    @pytest.mark.asyncio
    async def test_tool_slot_alias_reroutes_to_structured_playbook(self):
        launcher = SimpleNamespace(
            launch=AsyncMock(return_value={"execution_id": "exec-2"})
        )
        orch = make_orchestrator(
            execution_launcher=launcher,
            session=FakeSession(),
            profile_id="user-1",
            available_playbooks_cache="- cs_create_schedule: Create Schedule\n",
        )
        phases = [
            FakePhaseIR(
                id="phase_0",
                name="Create schedule",
                preferred_engine="tool:content_scheduler.cs_schedule_create",
                tool_name="content_scheduler.cs_schedule_create",
                input_params={"posts": ["p1"]},
            )
        ]
        items = [
            {
                "title": "Create schedule",
                "tool_name": "content_scheduler.cs_schedule_create",
                "input_params": {"posts": ["p1"]},
            }
        ]

        result = await orch.execute(task_ir=FakeTaskIR(phases=phases), action_items=items)

        assert result["status"] == "ok"
        launcher.launch.assert_awaited_once()
        assert launcher.launch.await_args.kwargs["playbook_code"] == "cs_create_schedule"
        assert phases[0].preferred_engine == "playbook:cs_create_schedule"
        assert items[0]["playbook_code"] == "cs_create_schedule"

    @pytest.mark.asyncio
    async def test_tool_slot_alias_reroutes_to_structured_playbook_without_cache(self):
        launcher = SimpleNamespace(
            launch=AsyncMock(return_value={"execution_id": "exec-2b"})
        )
        orch = make_orchestrator(
            execution_launcher=launcher,
            session=FakeSession(),
            profile_id="user-1",
            available_playbooks_cache="",
        )
        phases = [
            FakePhaseIR(
                id="phase_0",
                name="Create schedule",
                preferred_engine="tool:content_scheduler.cs_schedule_create",
                tool_name="content_scheduler.cs_schedule_create",
                input_params={"posts": ["p1"]},
            )
        ]
        items = [
            {
                "title": "Create schedule",
                "tool_name": "content_scheduler.cs_schedule_create",
                "input_params": {"posts": ["p1"]},
            }
        ]

        result = await orch.execute(task_ir=FakeTaskIR(phases=phases), action_items=items)

        assert result["status"] == "ok"
        launcher.launch.assert_awaited_once()
        assert launcher.launch.await_args.kwargs["playbook_code"] == "cs_create_schedule"
        assert phases[0].preferred_engine == "playbook:cs_create_schedule"
        assert items[0]["playbook_code"] == "cs_create_schedule"
