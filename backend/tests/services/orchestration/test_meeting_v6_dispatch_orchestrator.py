import pytest
from unittest.mock import MagicMock

from meeting_v6_test_support import bind_fake_dispatch_phase


class TestPolicyGateSinglePath:
    """Policy-blocked items are skipped in DispatchOrchestrator."""

    @pytest.mark.asyncio
    async def test_single_path_skips_blocked(self):
        from backend.app.services.orchestration.dispatch_orchestrator import (
            DispatchOrchestrator,
        )
        from backend.app.models.task_ir import TaskIR, PhaseIR

        orch = DispatchOrchestrator(
            session=MagicMock(id="sess-001", workspace_id="ws-default", metadata={}),
            profile_id="user-001",
            tasks_store=MagicMock(create_task=MagicMock(return_value="t-1")),
        )
        bind_fake_dispatch_phase(orch)
        phases = [
            PhaseIR(id="p1", name="Good"),
            PhaseIR(id="p2", name="Blocked"),
        ]
        task_ir = TaskIR(
            task_id="t-001",
            intent_instance_id="i-001",
            workspace_id="ws-default",
            actor_id="user-001",
            phases=phases,
        )
        action_items = [
            {"title": "Good", "description": "ok"},
            {
                "title": "Blocked",
                "description": "blocked",
                "landing_status": "policy_blocked",
            },
        ]
        result = await orch.execute(task_ir, action_items)
        assert result["succeeded"] >= 1
        assert result["skipped"] >= 1

class TestSinglePathWorkspaceKey:
    """DispatchOrchestrator records correct target workspace."""

    @pytest.mark.asyncio
    async def test_non_default_target_workspace_key(self):
        from backend.app.services.orchestration.dispatch_orchestrator import (
            DispatchOrchestrator,
        )
        from backend.app.models.task_ir import TaskIR, PhaseIR

        orch = DispatchOrchestrator(
            session=MagicMock(id="sess-001", workspace_id="ws-default", metadata={}),
            profile_id="user-001",
            tasks_store=MagicMock(create_task=MagicMock(return_value="t-1")),
        )
        bind_fake_dispatch_phase(orch)
        phases = [
            PhaseIR(id="p1", name="Task", target_workspace_id="ws-other"),
        ]
        task_ir = TaskIR(
            task_id="t-001",
            intent_instance_id="i-001",
            workspace_id="ws-default",
            actor_id="user-001",
            phases=phases,
        )
        action_items = [
            {"title": "Task", "description": "ok", "target_workspace_id": "ws-other"},
        ]
        result = await orch.execute(task_ir, action_items)
        assert result["succeeded"] == 1
        assert "ws-other" in result["workspaces"]

class TestMultiAllPolicyBlocked:
    """All items policy_blocked → DispatchOrchestrator reports all_failed."""

    @pytest.mark.asyncio
    async def test_all_policy_blocked_gives_all_failed(self):
        from backend.app.services.orchestration.dispatch_orchestrator import (
            DispatchOrchestrator,
        )
        from backend.app.models.task_ir import TaskIR, PhaseIR

        orch = DispatchOrchestrator(
            session=MagicMock(id="sess-001", workspace_id="ws-default", metadata={}),
            profile_id="user-001",
        )
        phases = [
            PhaseIR(id="p1", name="A", target_workspace_id="ws-a"),
            PhaseIR(id="p2", name="B", target_workspace_id="ws-b"),
        ]
        task_ir = TaskIR(
            task_id="t-001",
            intent_instance_id="i-001",
            workspace_id="ws-default",
            actor_id="user-001",
            phases=phases,
        )
        action_items = [
            {
                "title": "A",
                "description": "a",
                "landing_status": "policy_blocked",
            },
            {
                "title": "B",
                "description": "b",
                "landing_status": "policy_blocked",
            },
        ]
        result = await orch.execute(task_ir, action_items)
        assert result["total"] == 2
        assert result["succeeded"] == 0
        assert result["status"] == "all_failed"
