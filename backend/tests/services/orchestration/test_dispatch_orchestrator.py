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
    source_intent_id: Optional[str] = None
    description: str = ""
    status: str = "pending"
    preferred_engine: Optional[str] = None
    target_workspace_id: Optional[str] = None
    tool_name: Optional[str] = None
    input_params: Optional[dict] = None
    depends_on: Optional[List[str]] = None
    blocked_by: Optional[List[int]] = None
    latest_attempt_id: Optional[str] = None
    capability_profile: Optional[str] = None


@dataclass
class FakeTaskIR:
    task_id: str = "task-ir-1"
    phases: List[Any] = field(default_factory=list)


@dataclass
class FakeSession:
    id: str = "session-1"
    workspace_id: str = "ws-default"
    thread_id: str = "thread-1"
    metadata: Dict[str, Any] = field(default_factory=dict)


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
            FakePhaseIR(id="a", source_intent_id="intent-a", name="A"),
            FakePhaseIR(id="b", source_intent_id="intent-b", name="B", depends_on=["a"]),
        ]
        items = [
            {"title": "A", "intent_id": "intent-a", "landing_status": "policy_blocked"},
            {"title": "B", "intent_id": "intent-b", "description": ""},
        ]
        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        assert result["skipped"] >= 1  # B should be skipped
        assert items[1]["landing_status"] == "dependency_blocked"
        assert items[1]["skip_reason"] == "upstream_dependency_failed"
        assert items[1]["source_intent_id"] == "intent-b"
        assert items[1]["source_phase_id"] == "b"

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


class TestPhaseInputNormalization:
    """Deterministic hydration for weakly-specified meeting phases."""

    @pytest.mark.asyncio
    async def test_process_papers_pipeline_derives_query_from_dependencies(self):
        orch = DispatchOrchestrator(session=FakeSession(), profile_id="user-1")
        phases = [
            FakePhaseIR(
                id="fetch_a",
                name="Fetch A",
                tool_name="frontier_research.fetch_academic",
                input_params={"query": "autonomic nervous system", "max_results": 1},
            ),
            FakePhaseIR(
                id="fetch_b",
                name="Fetch B",
                tool_name="frontier_research.fetch_academic",
                input_params={"query": "autonomic nervous system", "max_results": 9},
            ),
            FakePhaseIR(
                id="process",
                name="Process",
                tool_name="frontier_research.process_papers_pipeline",
                depends_on=["fetch_a", "fetch_b"],
                input_params={},
            ),
        ]

        await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=[{"title": "Fetch A"}, {"title": "Fetch B"}, {"title": "Process"}],
        )

        assert phases[2].input_params["query"] == "autonomic nervous system"
        assert phases[2].input_params["max_results"] == 10

    @pytest.mark.asyncio
    async def test_article_draft_hydrates_workspace_topic_and_ig_format(self):
        session = FakeSession(workspace_id="ws-yoga")
        orch = DispatchOrchestrator(session=session, profile_id="user-1")
        phases = [
            FakePhaseIR(
                id="fetch",
                name="Fetch",
                tool_name="frontier_research.fetch_academic",
                input_params={"query": "autonomic nervous system", "max_results": 3},
            ),
            FakePhaseIR(
                id="draft",
                name="Generate IG Post Drafts",
                preferred_engine="playbook:article_draft",
                depends_on=["fetch"],
                input_params={"post_count": 3, "source_uri": "artifact://phase_4/output.pdf"},
            ),
        ]

        await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=[{"title": "Fetch"}, {"title": "Generate IG Post Drafts"}],
        )

        assert phases[1].input_params["topic"] == "autonomic nervous system"
        assert phases[1].input_params["workspace_id"] == "ws-yoga"
        assert phases[1].input_params["sources"] == ["pubmed", "semantic_scholar"]
        assert phases[1].input_params["language"] == "zh-TW"
        assert phases[1].input_params["target_format"] == "ig_caption"


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


class TestLineageFallbacks:
    @pytest.mark.asyncio
    async def test_phase_index_fallback_updates_tool_action_item(self):
        tasks_store = MagicMock()
        orch = DispatchOrchestrator(
            session=FakeSession(),
            profile_id="user-1",
            project_id="proj-1",
            tasks_store=tasks_store,
        )
        phases = [
            FakePhaseIR(
                id="phase_1",
                name="Renamed Tool Phase",
                tool_name="openseo.save_to_markdown",
            )
        ]
        items = [
            {"title": "Unrelated planning item", "intent_id": "intent-0"},
            {"title": "Original save item", "intent_id": "intent-1"},
        ]

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=items,
        )

        assert result["status"] == "ok"
        assert items[1]["landing_status"] == "task_created"
        assert items[1]["task_id"]
        assert items[1]["execution_id"] == items[1]["task_id"]

    @pytest.mark.asyncio
    async def test_phase_index_fallback_preserves_nested_playbook_execution_id(self):
        execution_launcher = MagicMock()
        execution_launcher.launch = AsyncMock(
            return_value={
                "execution_mode": "conversation",
                "result": {"execution_id": "exec-123"},
            }
        )
        orch = DispatchOrchestrator(
            session=FakeSession(),
            profile_id="user-1",
            project_id="proj-1",
            execution_launcher=execution_launcher,
        )
        phases = [
            FakePhaseIR(
                id="phase_0",
                name="Renamed Playbook Phase",
                preferred_engine="playbook:project_breakdown",
            )
        ]
        items = [
            {"title": "Original project breakdown item", "intent_id": "intent-0"},
        ]

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=items,
        )

        assert result["status"] == "ok"
        assert items[0]["landing_status"] == "launched"
        assert items[0]["execution_id"] == "exec-123"


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
        phases = [FakePhaseIR(id="a", source_intent_id="intent-a", name="Blocked")]
        items = [
            {
                "title": "Blocked",
                "intent_id": "intent-a",
                "landing_status": "policy_blocked",
            }
        ]
        result = await orchestrator.execute(
            task_ir=FakeTaskIR(phases=phases), action_items=items
        )
        # Blocked phases are "completed" with skipped status in the attempt
        attempt = orchestrator.get_attempt("a")
        assert attempt is not None
        assert attempt.status == AttemptStatus.SKIPPED
        assert items[0]["source_intent_id"] == "intent-a"
        assert items[0]["source_phase_id"] == "a"


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


class TestExecutionLineage:
    """Execution lineage is written back to the matched action item."""

    @pytest.mark.asyncio
    async def test_tool_dispatch_matches_by_intent_id_and_writes_lineage(
        self, monkeypatch
    ):
        orch = DispatchOrchestrator(session=FakeSession(), profile_id="user-1")
        phase = FakePhaseIR(
            id="intent-123",
            name="Compile Execution Plan",
            tool_name="tools.execute_plan",
        )
        action_item = {
            "title": "Human-facing title that does not match the phase name",
            "intent_id": "intent-123",
        }

        monkeypatch.setattr(
            orch,
            "_dispatch_tool",
            AsyncMock(
                return_value={
                    "task_id": "task-123",
                    "execution_id": "task-123",
                    "tool_name": "tools.execute_plan",
                }
            ),
        )

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=[phase]),
            action_items=[action_item],
        )

        assert result["status"] == "ok"
        assert result["succeeded"] == 1
        assert action_item["landing_status"] == "task_created"
        assert action_item["task_id"] == "task-123"
        assert action_item["execution_id"] == "task-123"
        attempt = orch.get_attempt("intent-123")
        assert attempt is not None
        assert attempt.result["execution_id"] == "task-123"

    @pytest.mark.asyncio
    async def test_tool_dispatch_prefers_source_intent_id_over_ordinal_phase_id(
        self, monkeypatch
    ):
        orch = DispatchOrchestrator(session=FakeSession(), profile_id="user-1")
        phase = FakePhaseIR(
            id="phase_0",
            source_intent_id="intent-2",
            name="Expanded execution phase",
            tool_name="tools.execute_plan",
        )
        items = [
            {"title": "Planning-only item", "intent_id": "intent-1"},
            {"title": "Actual execution item", "intent_id": "intent-2"},
        ]

        monkeypatch.setattr(
            orch,
            "_dispatch_tool",
            AsyncMock(
                return_value={
                    "task_id": "task-222",
                    "execution_id": "task-222",
                    "tool_name": "tools.execute_plan",
                }
            ),
        )

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=[phase]),
            action_items=items,
        )

        assert result["status"] == "ok"
        assert "execution_id" not in items[0]
        assert items[1]["landing_status"] == "task_created"
        assert items[1]["execution_id"] == "task-222"
        assert items[1]["execution_ids"] == ["task-222"]

    @pytest.mark.asyncio
    async def test_multiple_phases_same_source_intent_collect_lineage_without_overwrite(
        self, monkeypatch
    ):
        orch = DispatchOrchestrator(session=FakeSession(), profile_id="user-1")
        phases = [
            FakePhaseIR(
                id="phase_0",
                source_intent_id="intent-1",
                name="Prepare draft",
                tool_name="tools.prepare",
            ),
            FakePhaseIR(
                id="phase_1",
                source_intent_id="intent-1",
                name="Finalize draft",
                tool_name="tools.finalize",
                depends_on=["phase_0"],
            ),
        ]
        item = {"title": "Draft partner brief", "intent_id": "intent-1"}

        monkeypatch.setattr(
            orch,
            "_dispatch_tool",
            AsyncMock(
                side_effect=[
                    {
                        "task_id": "task-1",
                        "execution_id": "task-1",
                        "tool_name": "tools.prepare",
                    },
                    {
                        "task_id": "task-2",
                        "execution_id": "task-2",
                        "tool_name": "tools.finalize",
                    },
                ]
            ),
        )

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=[item],
        )

        assert result["status"] == "ok"
        assert item["execution_id"] == "task-1"
        assert item["task_id"] == "task-1"
        assert item["execution_ids"] == ["task-1", "task-2"]
        assert item["task_ids"] == ["task-1", "task-2"]


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
