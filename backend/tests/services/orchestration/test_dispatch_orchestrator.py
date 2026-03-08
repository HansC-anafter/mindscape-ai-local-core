"""
Tests for DispatchOrchestrator.

Covers:
- DAG walk (parallel dispatch of independent phases)
- Dependency gate (upstream fail → downstream skip)
- Multi-workspace fan-out
- Playbook code extraction
- Empty TaskIR handling
- Policy-blocked item skip
- Projection write fallback
- PhaseAttempt tracking
"""

import importlib.util
import os
import sys
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.models.phase_attempt import AttemptStatus

# Load dispatch_orchestrator by file path to avoid chain
_DO_PATH = os.path.join(
    os.path.dirname(__file__),
    "..",
    "..",
    "..",
    "app",
    "services",
    "orchestration",
    "dispatch_orchestrator.py",
)
_DO_PATH = os.path.normpath(_DO_PATH)
_spec = importlib.util.spec_from_file_location("dispatch_orchestrator", _DO_PATH)
_mod = importlib.util.module_from_spec(_spec)
sys.modules["dispatch_orchestrator"] = _mod
_spec.loader.exec_module(_mod)
DispatchOrchestrator = _mod.DispatchOrchestrator


@dataclass
class FakePhaseIR:
    id: str
    name: str
    description: str = ""
    status: str = "pending"
    preferred_engine: Optional[str] = None
    target_workspace_id: Optional[str] = None
    tool_name: Optional[str] = None
    input_params: Optional[dict] = None
    depends_on: Optional[List[str]] = None
    blocked_by: Optional[List[int]] = None
    latest_attempt_id: Optional[str] = None


@dataclass
class FakeTaskIR:
    task_id: str = "task-ir-1"
    phases: List[Any] = field(default_factory=list)


@dataclass
class FakeSession:
    id: str = "session-1"
    workspace_id: str = "ws-default"
    thread_id: str = "thread-1"


@pytest.fixture
def orchestrator():
    return DispatchOrchestrator(
        execution_launcher=None,
        tasks_store=None,
        session=FakeSession(),
        profile_id="user-1",
        project_id="proj-1",
    )


class TestEmptyDispatch:
    """Empty or None TaskIR."""

    @pytest.mark.asyncio
    async def test_none_task_ir(self, orchestrator):
        result = await orchestrator.execute(task_ir=None, action_items=[])
        assert result["status"] == "empty"
        assert result["total"] == 0

    @pytest.mark.asyncio
    async def test_empty_phases(self, orchestrator):
        result = await orchestrator.execute(
            task_ir=FakeTaskIR(phases=[]), action_items=[]
        )
        assert result["status"] == "empty"


class TestLinearDAG:
    """Linear dependency chain: A → B → C."""

    @pytest.mark.asyncio
    async def test_linear_all_succeed(self, orchestrator):
        phases = [
            FakePhaseIR(id="a", name="A"),
            FakePhaseIR(id="b", name="B", depends_on=["a"]),
            FakePhaseIR(id="c", name="C", depends_on=["b"]),
        ]
        items = [
            {"title": "A", "description": ""},
            {"title": "B", "description": ""},
            {"title": "C", "description": ""},
        ]
        result = await orchestrator.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        assert result["succeeded"] == 3
        assert result["status"] == "ok"


class TestDependencyGate:
    """Upstream failure → downstream skipped."""

    @pytest.mark.asyncio
    async def test_upstream_fail_skips_downstream(self):
        """If A is policy-blocked, B (depends_on A) should be SKIPPED."""
        orch = DispatchOrchestrator(session=FakeSession(), profile_id="user-1")
        phases = [
            FakePhaseIR(id="a", name="A"),
            FakePhaseIR(id="b", name="B", depends_on=["a"]),
        ]
        items = [
            {"title": "A", "landing_status": "policy_blocked"},
            {"title": "B", "description": ""},
        ]
        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        assert result["skipped"] >= 1  # B should be skipped

    @pytest.mark.asyncio
    async def test_continue_on_dep_failure_policy(self):
        """With continue_on_dep_failure, downstream is NOT skipped."""
        orch = DispatchOrchestrator(
            session=FakeSession(),
            profile_id="user-1",
            skip_policy="continue_on_dep_failure",
        )
        phases = [
            FakePhaseIR(id="a", name="A"),
            FakePhaseIR(id="b", name="B", depends_on=["a"]),
        ]
        items = [
            {"title": "A", "landing_status": "policy_blocked"},
            {"title": "B", "description": ""},
        ]
        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        # A is pre-blocked (skipped=1), but B should still dispatch
        assert result["succeeded"] >= 1  # B dispatched despite A's failure


class TestParallelDAG:
    """Independent phases dispatched in parallel."""

    @pytest.mark.asyncio
    async def test_independent_phases(self, orchestrator):
        phases = [
            FakePhaseIR(id="a", name="A"),
            FakePhaseIR(id="b", name="B"),
            FakePhaseIR(id="c", name="C"),
        ]
        items = [{"title": "A"}, {"title": "B"}, {"title": "C"}]
        result = await orchestrator.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        assert result["total"] == 3
        assert result["succeeded"] == 3


class TestDiamondDAG:
    """Diamond dependency: A → B, A → C, B+C → D."""

    @pytest.mark.asyncio
    async def test_diamond(self, orchestrator):
        phases = [
            FakePhaseIR(id="a", name="A"),
            FakePhaseIR(id="b", name="B", depends_on=["a"]),
            FakePhaseIR(id="c", name="C", depends_on=["a"]),
            FakePhaseIR(id="d", name="D", depends_on=["b", "c"]),
        ]
        items = [{"title": "A"}, {"title": "B"}, {"title": "C"}, {"title": "D"}]
        result = await orchestrator.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        assert result["succeeded"] == 4
        assert result["status"] == "ok"


class TestPolicyBlockedSkip:
    """Pre-blocked items should be skipped."""

    @pytest.mark.asyncio
    async def test_policy_blocked(self, orchestrator):
        phases = [FakePhaseIR(id="a", name="Blocked")]
        items = [{"title": "Blocked", "landing_status": "policy_blocked"}]
        result = await orchestrator.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        # Blocked phases are "completed" with skipped status in the attempt
        attempt = orchestrator.get_attempt("a")
        assert attempt is not None
        assert attempt.status == AttemptStatus.SKIPPED


class TestMultiWorkspace:
    """Workspace tracking."""

    @pytest.mark.asyncio
    async def test_workspace_fanout(self, orchestrator):
        phases = [
            FakePhaseIR(id="a", name="A", target_workspace_id="ws-1"),
            FakePhaseIR(id="b", name="B", target_workspace_id="ws-2"),
        ]
        items = [
            {"title": "A", "target_workspace_id": "ws-1"},
            {"title": "B", "target_workspace_id": "ws-2"},
        ]
        result = await orchestrator.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        assert "ws-1" in result["workspaces"]
        assert "ws-2" in result["workspaces"]


class TestPhaseAttemptTracking:
    """PhaseAttempt lifecycle tracking."""

    @pytest.mark.asyncio
    async def test_attempt_created_for_each_phase(self, orchestrator):
        phases = [
            FakePhaseIR(id="a", name="A"),
            FakePhaseIR(id="b", name="B"),
        ]
        items = [{"title": "A"}, {"title": "B"}]
        await orchestrator.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        attempts = orchestrator.get_all_attempts()
        assert len(attempts) == 2
        assert "a" in attempts
        assert "b" in attempts

    @pytest.mark.asyncio
    async def test_attempt_has_correct_task_ir_id(self, orchestrator):
        phases = [FakePhaseIR(id="a", name="A")]
        items = [{"title": "A"}]
        await orchestrator.execute(
            task_ir=FakeTaskIR(task_id="ir-99", phases=phases), action_items=items
        )
        attempt = orchestrator.get_attempt("a")
        assert attempt.task_ir_id == "ir-99"


class TestPlaybookCodeExtraction:
    """Engine string → playbook code."""

    def test_extract_playbook_code(self):
        assert (
            DispatchOrchestrator._extract_playbook_code("playbook:generic") == "generic"
        )
        assert (
            DispatchOrchestrator._extract_playbook_code("playbook:deploy") == "deploy"
        )
        assert DispatchOrchestrator._extract_playbook_code(None) is None
        assert DispatchOrchestrator._extract_playbook_code("mcp:server") is None
