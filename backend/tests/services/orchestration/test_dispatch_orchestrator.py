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
from types import SimpleNamespace
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from backend.app.models.phase_attempt import AttemptStatus
from backend.app.models.workspace import TaskStatus

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
    metadata: Any = None


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


class _CapturingTasksStore:
    def __init__(self) -> None:
        self.created = []

    def create_task(self, task) -> None:
        self.created.append(task)


class _TerminalTrackingTasksStore:
    def __init__(self) -> None:
        self.created = []
        self.updated = []
        self.tasks = {}

    def create_task(self, task) -> None:
        self.created.append(task)
        self.tasks[task.id] = task

    def update_task_status(
        self,
        task_id,
        status,
        result=None,
        error=None,
        started_at=None,
        completed_at=None,
    ):
        task = self.tasks[task_id]
        task.status = status
        task.result = result
        task.error = error
        if started_at is not None:
            task.started_at = started_at
        if completed_at is not None:
            task.completed_at = completed_at
        self.updated.append(
            {
                "task_id": task_id,
                "status": status,
                "result": result,
                "error": error,
            }
        )
        return task

    def get_task(self, task_id):
        return self.tasks.get(task_id)


class TestToolDispatchInputs:
    @pytest.mark.asyncio
    async def test_review_tool_injects_profile_id_into_tool_inputs(self):
        store = _CapturingTasksStore()
        orch = DispatchOrchestrator(
            session=FakeSession(),
            profile_id="profile-123",
            tasks_store=store,
        )
        phase = FakePhaseIR(
            id="review-phase",
            name="Review Check",
            tool_name="review.maybe_suggest_review",
            input_params={},
        )

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=[phase]),
            action_items=[{"title": "Review Check"}],
        )

        assert result["succeeded"] == 1
        assert len(store.created) == 1
        task = store.created[0]
        assert task.status == TaskStatus.PENDING
        assert task.params["input_params"]["profile_id"] == "profile-123"
        assert task.execution_context["inputs"]["profile_id"] == "profile-123"

    @pytest.mark.asyncio
    async def test_external_agent_tool_executes_inline_and_marks_terminal(
        self, monkeypatch
    ):
        store = _TerminalTrackingTasksStore()
        orch = DispatchOrchestrator(
            session=FakeSession(),
            profile_id="profile-123",
            project_id="proj-123",
            tasks_store=store,
        )
        phase = FakePhaseIR(
            id="deliverable-phase",
            name="Deliverable",
            tool_name="core.external_agent_execute",
            input_params={
                "agent": "codex_cli",
                "task": "Write the markdown deliverable",
                "context": {
                    "workspace_id": "ws-default",
                    "workspace_storage_base": "/tmp/workspaces/ws-default",
                },
            },
        )

        class _FakeTool:
            async def execute(self, **kwargs):
                assert kwargs["agent"] == "codex_cli"
                return {
                    "success": True,
                    "output": "done",
                    "attachments": [
                        {
                            "filename": "persona_operating_system.md",
                            "content": "# Persona\n\ncontent",
                            "mime_type": "text/markdown",
                        }
                    ],
                    "execution_trace": {
                        "files_created": ["persona_operating_system.md"],
                        "files_modified": [],
                    },
                }

        class _FakeWorkspaceStore:
            async def get_workspace(self, workspace_id):
                return SimpleNamespace(
                    storage_base_path="/tmp/workspaces/ws-default",
                    artifacts_dir="artifacts",
                )

        class _FakeGovernanceEngine:
            def process_completion(self, **kwargs):
                return {
                    "success": True,
                    "execution_id": kwargs["execution_id"],
                    "artifact_id": "artifact-123",
                    "landing_failure": {},
                }

        monkeypatch.setattr(
            "backend.app.services.tools.registry.get_mindscape_tool",
            lambda tool_name: _FakeTool()
            if tool_name == "core.external_agent_execute"
            else None,
        )
        monkeypatch.setattr(
            "backend.app.services.tools.registry.register_external_agent_tools",
            lambda: [],
        )
        monkeypatch.setattr(
            "backend.app.services.orchestration.governance_engine.GovernanceEngine",
            _FakeGovernanceEngine,
        )
        monkeypatch.setattr(
            "backend.app.services.stores.postgres.workspaces_store.PostgresWorkspacesStore",
            _FakeWorkspaceStore,
        )

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=[phase]),
            action_items=[{"title": "Deliverable"}],
        )

        assert result["status"] == "ok"
        assert result["succeeded"] == 1
        assert len(store.created) == 1
        assert len(store.updated) == 1
        task = store.created[0]
        assert task.pack_id == "core.external_agent_execute"
        assert task.status == TaskStatus.SUCCEEDED
        assert task.result["governance"]["success"] is True


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


class TestActuatorBindingNormalization:
    @pytest.mark.asyncio
    async def test_tool_engine_with_playbook_code_reroutes_to_playbook_dispatch(
        self, monkeypatch
    ):
        execution_launcher = MagicMock()
        orch = DispatchOrchestrator(
            session=FakeSession(),
            profile_id="user-1",
            project_id="proj-1",
            execution_launcher=execution_launcher,
        )
        phase = FakePhaseIR(
            id="phase-playbook-rebind",
            source_intent_id="intent-playbook-rebind",
            name="Create persona operating system",
            tool_name="cis_mind_identity",
            preferred_engine="tool:cis_mind_identity",
        )
        action_item = {
            "title": "Create persona operating system",
            "intent_id": "intent-playbook-rebind",
        }

        monkeypatch.setattr(
            orch,
            "_is_registered_tool_name",
            lambda tool_name: False,
        )
        monkeypatch.setattr(
            orch,
            "_is_known_playbook_code",
            lambda playbook_code: playbook_code == "cis_mind_identity",
        )
        playbook_dispatch = AsyncMock(
            return_value={
                "execution_id": "exec-playbook-1",
                "playbook_code": "cis_mind_identity",
            }
        )
        tool_dispatch = AsyncMock()
        monkeypatch.setattr(orch, "_launch_playbook", playbook_dispatch)
        monkeypatch.setattr(orch, "_dispatch_tool", tool_dispatch)

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=[phase]),
            action_items=[action_item],
        )

        assert result["status"] == "ok"
        assert phase.preferred_engine == "playbook:cis_mind_identity"
        assert phase.tool_name is None
        playbook_dispatch.assert_awaited_once()
        tool_dispatch.assert_not_awaited()
        assert action_item["landing_status"] == "launched"
        assert action_item["execution_id"] == "exec-playbook-1"

    @pytest.mark.asyncio
    async def test_registered_tool_stays_on_tool_dispatch(
        self, monkeypatch
    ):
        execution_launcher = MagicMock()
        orch = DispatchOrchestrator(
            session=FakeSession(),
            profile_id="user-1",
            project_id="proj-1",
            execution_launcher=execution_launcher,
        )
        phase = FakePhaseIR(
            id="phase-tool-stays-tool",
            source_intent_id="intent-tool-stays-tool",
            name="Map brand lens",
            tool_name="brand_identity.cis_mapper_map",
            preferred_engine="tool:brand_identity.cis_mapper_map",
        )
        action_item = {
            "title": "Map brand lens",
            "intent_id": "intent-tool-stays-tool",
        }

        monkeypatch.setattr(
            orch,
            "_is_registered_tool_name",
            lambda tool_name: tool_name == "brand_identity.cis_mapper_map",
        )
        monkeypatch.setattr(
            orch,
            "_is_known_playbook_code",
            lambda playbook_code: False,
        )
        playbook_dispatch = AsyncMock()
        tool_dispatch = AsyncMock(
            return_value={
                "task_id": "task-tool-1",
                "execution_id": "task-tool-1",
                "tool_name": "brand_identity.cis_mapper_map",
            }
        )
        monkeypatch.setattr(orch, "_launch_playbook", playbook_dispatch)
        monkeypatch.setattr(orch, "_dispatch_tool", tool_dispatch)

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=[phase]),
            action_items=[action_item],
        )

        assert result["status"] == "ok"
        assert phase.preferred_engine == "tool:brand_identity.cis_mapper_map"
        assert phase.tool_name == "brand_identity.cis_mapper_map"
        tool_dispatch.assert_awaited_once()
        playbook_dispatch.assert_not_awaited()
        assert action_item["landing_status"] == "task_created"
        assert action_item["execution_id"] == "task-tool-1"


class TestDeliverableExternalAgentPromotion:
    @pytest.mark.asyncio
    async def test_only_terminal_markdown_deliverable_phase_reroutes_to_external_agent(
        self, monkeypatch
    ):
        session = FakeSession(
            workspace_id="ws-1",
            metadata={
                "executor_target_client_id": "client-e2e-001",
                "execution_context_snapshot": {"executor_runtime_id": "codex_cli"},
            },
        )
        orch = DispatchOrchestrator(
            session=session,
            profile_id="user-1",
            project_id="proj-1",
        )
        governance = SimpleNamespace(
            goals=["Land the final markdown deliverable inside the workspace."],
            requested_output_type="text/markdown",
            deliverables=[
                {
                    "name": "persona_operating_system.md",
                    "description": "品牌人格操作系統文件",
                    "mime_type": "text/markdown",
                }
            ],
        )

        upstream_phase = FakePhaseIR(
            id="ws-upstream",
            source_intent_id="intent-upstream",
            name="Build evidence ledger",
            description="Prepare the upstream evidence ledger before drafting the final persona file.",
            tool_name="cis_mind_identity",
            preferred_engine="playbook:cis_mind_identity",
            input_params={
                "deliverable_id": "D1",
                "deliverable_name": "persona_operating_system.md",
                "deliverable_path": "persona_operating_system.md",
            },
        )
        terminal_phase = FakePhaseIR(
            id="ws-terminal",
            source_intent_id="intent-terminal",
            name="Draft persona operating system",
            description="Create the final persona markdown deliverable.",
            tool_name="cis_mind_identity",
            preferred_engine="playbook:cis_mind_identity",
            input_params={
                "deliverable_id": "D1",
                "deliverable_name": "persona_operating_system.md",
                "deliverable_path": "persona_operating_system.md",
            },
            depends_on=["ws-upstream"],
        )
        action_items = [
            {
                "title": "Build evidence ledger",
                "intent_id": "intent-upstream",
                "description": "Prepare the upstream evidence ledger.",
            },
            {
                "title": "Draft persona operating system",
                "intent_id": "intent-terminal",
                "description": "Create the final persona markdown deliverable.",
            },
        ]

        monkeypatch.setattr(
            orch,
            "_resolve_workspace_runtime_context",
            AsyncMock(
                return_value={
                    "agent_id": "codex_cli",
                    "workspace_storage_base": "/tmp/ws-1",
                    "target_client_id": "client-e2e-001",
                }
            ),
        )
        external_dispatch = AsyncMock(
            return_value={
                "task_id": "task-terminal",
                "execution_id": "task-terminal",
                "tool_name": "core.external_agent_execute",
            }
        )
        monkeypatch.setattr(orch, "_execute_tool_inline", external_dispatch)

        task_ir = FakeTaskIR(
            phases=[upstream_phase, terminal_phase],
            metadata=SimpleNamespace(get_governance=lambda: governance),
        )
        result = await orch.execute(task_ir=task_ir, action_items=action_items)

        assert result["status"] == "ok"
        assert upstream_phase.tool_name != "core.external_agent_execute"
        assert terminal_phase.tool_name == "core.external_agent_execute"
        external_dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_markdown_deliverable_tool_phase_reroutes_to_external_agent(
        self, monkeypatch
    ):
        session = FakeSession(
            workspace_id="ws-1",
            metadata={
                "executor_target_client_id": "client-e2e-001",
                "execution_context_snapshot": {"executor_runtime_id": "codex_cli"},
            },
        )
        orch = DispatchOrchestrator(session=session, profile_id="user-1", project_id="proj-1")
        governance = SimpleNamespace(
            goals=["Publish a complete week-one Instagram rollout"],
            non_goals=["Do not make unverified growth claims"],
            human_instructions="Final output must land as markdown deliverables.",
            requested_output_type="text/markdown",
            deliverables=[
                {
                    "name": "instagram_week1_calendar.md",
                    "description": "第一週 Instagram post / reel 發布節奏",
                    "mime_type": "text/markdown",
                }
            ],
        )

        phase = FakePhaseIR(
            id="ws-deliverable-1",
            source_intent_id="intent-1",
            name="Draft week-one calendar",
            description="Turn the meeting decision into a publishable week-one IG calendar.",
            tool_name="ig.ig_template_engine_tool",
            preferred_engine="tool:ig.ig_template_engine_tool",
            input_params={
                "deliverable_id": "D2",
                "deliverable_name": "instagram_week1_calendar.md",
                "deliverable_path": "instagram_week1_calendar.md",
            },
        )
        action_item = {
            "title": "Draft week-one calendar",
            "intent_id": "intent-1",
            "description": "Create the final markdown calendar deliverable.",
        }

        monkeypatch.setattr(
            orch,
            "_resolve_workspace_runtime_context",
            AsyncMock(
                return_value={
                    "agent_id": "codex_cli",
                    "workspace_storage_base": "/tmp/ws-1",
                    "target_client_id": "client-e2e-001",
                }
            ),
        )
        monkeypatch.setattr(
            orch,
            "_execute_tool_inline",
            AsyncMock(
                return_value={
                    "task_id": "task-external-1",
                    "execution_id": "task-external-1",
                    "tool_name": "core.external_agent_execute",
                }
            ),
        )

        task_ir = FakeTaskIR(
            phases=[phase],
            metadata=SimpleNamespace(get_governance=lambda: governance),
        )
        result = await orch.execute(task_ir=task_ir, action_items=[action_item])

        assert result["status"] == "ok"
        assert phase.tool_name == "core.external_agent_execute"
        assert phase.preferred_engine == "tool:core.external_agent_execute"
        assert phase.input_params["agent"] == "codex_cli"
        assert "instagram_week1_calendar.md" in phase.input_params["task"]
        assert (
            phase.input_params["context"]["workspace_storage_base"] == "/tmp/ws-1"
        )
        assert phase.input_params["context"]["target_client_id"] == "client-e2e-001"
        assert (
            phase.input_params["context"]["deliverable_path"]
            == "instagram_week1_calendar.md"
        )
        assert action_item["landing_status"] == "task_created"

    @pytest.mark.asyncio
    async def test_markdown_deliverable_agent_phase_without_tool_reroutes_to_external_agent(
        self, monkeypatch
    ):
        session = FakeSession(
            workspace_id="ws-1",
            metadata={
                "executor_target_client_id": "client-e2e-001",
                "execution_context_snapshot": {"executor_runtime_id": "codex_cli"},
            },
        )
        orch = DispatchOrchestrator(session=session, profile_id="user-1", project_id="proj-1")
        governance = SimpleNamespace(
            goals=["Publish a complete week-one Instagram rollout"],
            requested_output_type="text/markdown",
            deliverables=[
                {
                    "name": "persona_operating_system.md",
                    "description": "品牌人格操作系統文件",
                    "mime_type": "text/markdown",
                }
            ],
        )

        phase = FakePhaseIR(
            id="ws-deliverable-2",
            source_intent_id="intent-2",
            name="Draft persona operating system",
            description="Create the final persona markdown deliverable.",
            tool_name=None,
            preferred_engine="agent:auto",
            input_params={
                "deliverable_id": "D1",
                "deliverable_name": "persona_operating_system.md",
                "deliverable_path": "persona_operating_system.md",
            },
        )
        action_item = {
            "title": "Draft persona operating system",
            "intent_id": "intent-2",
            "description": "Create the final persona markdown deliverable.",
        }

        monkeypatch.setattr(
            orch,
            "_resolve_workspace_runtime_context",
            AsyncMock(
                return_value={
                    "agent_id": "codex_cli",
                    "workspace_storage_base": "/tmp/ws-1",
                    "target_client_id": "client-e2e-001",
                }
            ),
        )
        monkeypatch.setattr(
            orch,
            "_execute_tool_inline",
            AsyncMock(
                return_value={
                    "task_id": "task-external-2",
                    "execution_id": "task-external-2",
                    "tool_name": "core.external_agent_execute",
                }
            ),
        )

        task_ir = FakeTaskIR(
            phases=[phase],
            metadata=SimpleNamespace(get_governance=lambda: governance),
        )
        result = await orch.execute(task_ir=task_ir, action_items=[action_item])

        assert result["status"] == "ok"
        assert phase.tool_name == "core.external_agent_execute"
        assert phase.preferred_engine == "tool:core.external_agent_execute"
        assert phase.input_params["agent"] == "codex_cli"
        assert "persona_operating_system.md" in phase.input_params["task"]
        assert (
            phase.input_params["context"]["deliverable_path"]
            == "persona_operating_system.md"
        )

    @pytest.mark.asyncio
    async def test_markdown_deliverable_action_item_targets_reroute_to_external_agent(
        self, monkeypatch
    ):
        session = FakeSession(
            workspace_id="ws-1",
            metadata={
                "executor_target_client_id": "client-e2e-001",
                "execution_context_snapshot": {"executor_runtime_id": "codex_cli"},
            },
        )
        orch = DispatchOrchestrator(session=session, profile_id="user-1", project_id="proj-1")
        governance = SimpleNamespace(
            goals=["Land the final markdown deliverable inside the workspace."],
            requested_output_type="text/markdown",
            deliverables=[
                {
                    "name": "persona_operating_system.md",
                    "description": "品牌人格操作系統文件",
                    "mime_type": "text/markdown",
                }
            ],
        )

        phase = FakePhaseIR(
            id="ws-deliverable-3",
            source_intent_id="intent-3",
            name="Refine persona operating system",
            description="Promote the deliverable-bound workstream to a markdown writer.",
            tool_name="brand_identity.cis_mapper_map",
            preferred_engine="tool:brand_identity.cis_mapper_map",
            input_params={"workspace_id": "ws-1"},
        )
        action_item = {
            "title": "Refine persona operating system",
            "intent_id": "intent-3",
            "description": "Create the final markdown persona deliverable.",
            "input_params": {
                "workspace_id": "ws-1",
                "deliverable_id": "D1",
                "deliverable_name": "persona_operating_system.md",
                "deliverable_path": "persona_operating_system.md",
            },
        }

        monkeypatch.setattr(
            orch,
            "_resolve_workspace_runtime_context",
            AsyncMock(
                return_value={
                    "agent_id": "codex_cli",
                    "workspace_storage_base": "/tmp/ws-1",
                    "target_client_id": "client-e2e-001",
                }
            ),
        )
        monkeypatch.setattr(
            orch,
            "_execute_tool_inline",
            AsyncMock(
                return_value={
                    "task_id": "task-external-3",
                    "execution_id": "task-external-3",
                    "tool_name": "core.external_agent_execute",
                }
            ),
        )

        task_ir = FakeTaskIR(
            phases=[phase],
            metadata=SimpleNamespace(get_governance=lambda: governance),
        )
        result = await orch.execute(task_ir=task_ir, action_items=[action_item])

        assert result["status"] == "ok"
        assert phase.tool_name == "core.external_agent_execute"
        assert phase.preferred_engine == "tool:core.external_agent_execute"
        assert phase.input_params["agent"] == "codex_cli"
        assert "persona_operating_system.md" in phase.input_params["task"]
        assert (
            phase.input_params["context"]["deliverable_path"]
            == "persona_operating_system.md"
        )

    @pytest.mark.asyncio
    async def test_markdown_deliverable_reroutes_with_fallback_workspace_storage_base(
        self, monkeypatch
    ):
        session = FakeSession(
            workspace_id="ws-memory-engine-e2e-codex-054234",
            metadata={
                "executor_target_client_id": "client-e2e-001",
                "execution_context_snapshot": {"executor_runtime_id": "codex_cli"},
            },
        )
        orch = DispatchOrchestrator(
            session=session,
            profile_id="user-1",
            project_id="proj-1",
        )
        governance = SimpleNamespace(
            goals=["Land the final markdown deliverable inside the workspace."],
            requested_output_type="text/markdown",
            deliverables=[
                {
                    "name": "instagram_week1_calendar.md",
                    "description": "第一週 Instagram post / reel 發布節奏",
                    "mime_type": "text/markdown",
                }
            ],
        )

        phase = FakePhaseIR(
            id="ws-deliverable-fallback",
            source_intent_id="intent-fallback",
            name="Draft week-one calendar",
            description="Create the final markdown calendar deliverable.",
            tool_name="ig.ig_template_engine_tool",
            preferred_engine="tool:ig.ig_template_engine_tool",
            input_params={
                "deliverable_id": "D2",
                "deliverable_name": "instagram_week1_calendar.md",
                "deliverable_path": "instagram_week1_calendar.md",
            },
        )
        action_item = {
            "title": "Draft week-one calendar",
            "intent_id": "intent-fallback",
            "description": "Create the final markdown calendar deliverable.",
        }

        monkeypatch.setattr(
            "backend.app.services.stores.postgres.workspaces_store.PostgresWorkspacesStore.get_workspace",
            AsyncMock(return_value=None),
        )
        monkeypatch.setattr(
            orch,
            "_execute_tool_inline",
            AsyncMock(
                return_value={
                    "task_id": "task-external-fallback",
                    "execution_id": "task-external-fallback",
                    "tool_name": "core.external_agent_execute",
                }
            ),
        )

        task_ir = FakeTaskIR(
            phases=[phase],
            metadata=SimpleNamespace(get_governance=lambda: governance),
        )
        result = await orch.execute(task_ir=task_ir, action_items=[action_item])

        assert result["status"] == "ok"
        assert phase.tool_name == "core.external_agent_execute"
        assert phase.preferred_engine == "tool:core.external_agent_execute"
        assert phase.input_params["agent"] == "codex_cli"
        assert (
            phase.input_params["context"]["workspace_storage_base"]
            == "/tmp/mindscape/workspaces/ws-memory-engine-e2e-codex-054234"
        )
        assert phase.input_params["context"]["target_client_id"] == "client-e2e-001"

    @pytest.mark.asyncio
    async def test_markdown_deliverable_playbook_phase_reroutes_to_external_agent(
        self, monkeypatch
    ):
        session = FakeSession(
            workspace_id="ws-1",
            metadata={
                "executor_target_client_id": "client-e2e-001",
                "execution_context_snapshot": {"executor_runtime_id": "codex_cli"},
            },
        )
        orch = DispatchOrchestrator(
            session=session,
            profile_id="user-1",
            project_id="proj-1",
        )
        governance = SimpleNamespace(
            goals=["Land the final markdown deliverable inside the workspace."],
            requested_output_type="text/markdown",
            deliverables=[
                {
                    "name": "instagram_week1_calendar.md",
                    "description": "第一週 Instagram post / reel 發布節奏",
                    "mime_type": "text/markdown",
                }
            ],
        )

        phase = FakePhaseIR(
            id="ws-deliverable-playbook",
            source_intent_id="intent-playbook",
            name="Draft week-one calendar",
            description="Create the final markdown calendar deliverable.",
            tool_name="week1_feed_factory",
            preferred_engine="playbook:week1_feed_factory",
            input_params={
                "deliverable_id": "D2",
                "deliverable_name": "instagram_week1_calendar.md",
                "deliverable_path": "instagram_week1_calendar.md",
            },
        )
        action_item = {
            "title": "Draft week-one calendar",
            "intent_id": "intent-playbook",
            "description": "Create the final markdown calendar deliverable.",
        }

        monkeypatch.setattr(
            orch,
            "_resolve_workspace_runtime_context",
            AsyncMock(
                return_value={
                    "agent_id": "codex_cli",
                    "workspace_storage_base": "/tmp/ws-1",
                    "target_client_id": "client-e2e-001",
                }
            ),
        )
        monkeypatch.setattr(
            orch,
            "_execute_tool_inline",
            AsyncMock(
                return_value={
                    "task_id": "task-external-playbook",
                    "execution_id": "task-external-playbook",
                    "tool_name": "core.external_agent_execute",
                }
            ),
        )

        task_ir = FakeTaskIR(
            phases=[phase],
            metadata=SimpleNamespace(get_governance=lambda: governance),
        )
        result = await orch.execute(task_ir=task_ir, action_items=[action_item])

        assert result["status"] == "ok"
        assert phase.tool_name == "core.external_agent_execute"
        assert phase.preferred_engine == "tool:core.external_agent_execute"
        assert phase.input_params["agent"] == "codex_cli"
        assert "instagram_week1_calendar.md" in phase.input_params["task"]

    @pytest.mark.asyncio
    async def test_required_input_policy_blocked_markdown_deliverable_reroutes_and_dispatches(
        self, monkeypatch
    ):
        session = FakeSession(
            workspace_id="ws-1",
            metadata={
                "executor_target_client_id": "client-e2e-001",
                "execution_context_snapshot": {"executor_runtime_id": "codex_cli"},
            },
        )
        orch = DispatchOrchestrator(
            session=session,
            profile_id="user-1",
            project_id="proj-1",
        )
        governance = SimpleNamespace(
            goals=["Land the final markdown deliverable inside the workspace."],
            requested_output_type="text/markdown",
            deliverables=[
                {
                    "name": "reel_hook_bank.md",
                    "description": "可直接使用的短影音 hook bank",
                    "mime_type": "text/markdown",
                }
            ],
        )

        phase = FakePhaseIR(
            id="ws-reel-hooks",
            source_intent_id="intent-reel-hooks",
            name="Draft reel hook bank",
            description="Create the final reel hook bank markdown deliverable.",
            tool_name="ig.ig_complete_workflow_tool",
            preferred_engine="tool:ig.ig_complete_workflow_tool",
            input_params={
                "deliverable_id": "D3",
                "deliverable_name": "reel_hook_bank.md",
                "deliverable_path": "reel_hook_bank.md",
            },
        )
        action_item = {
            "title": "Draft reel hook bank",
            "intent_id": "intent-reel-hooks",
            "description": "Create the final reel hook bank markdown deliverable.",
            "landing_status": "policy_blocked",
            "policy_reason_code": "REQUIRED_INPUT_MISSING",
            "landing_error": "Playbook 'ig_post_generation' missing required inputs ['source_content']",
            "policy_blocks": [
                {
                    "reason_code": "REQUIRED_INPUT_MISSING",
                    "missing_fields": ["source_content"],
                }
            ],
        }

        monkeypatch.setattr(
            orch,
            "_resolve_workspace_runtime_context",
            AsyncMock(
                return_value={
                    "agent_id": "codex_cli",
                    "workspace_storage_base": "/tmp/ws-1",
                    "target_client_id": "client-e2e-001",
                }
            ),
        )
        monkeypatch.setattr(
            orch,
            "_execute_tool_inline",
            AsyncMock(
                return_value={
                    "task_id": "task-external-hooks",
                    "execution_id": "task-external-hooks",
                    "tool_name": "core.external_agent_execute",
                }
            ),
        )

        task_ir = FakeTaskIR(
            phases=[phase],
            metadata=SimpleNamespace(get_governance=lambda: governance),
        )
        result = await orch.execute(task_ir=task_ir, action_items=[action_item])

        assert result["status"] == "ok"
        assert phase.tool_name == "core.external_agent_execute"
        assert action_item["landing_status"] == "task_created"
        assert "landing_error" not in action_item
        assert "policy_blocks" not in action_item


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
