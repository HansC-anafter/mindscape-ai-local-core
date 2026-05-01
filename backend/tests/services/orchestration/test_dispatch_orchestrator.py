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
from types import SimpleNamespace
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
    metadata: Dict[str, Any] = field(default_factory=dict)
    agenda: List[str] = field(default_factory=list)


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


class TestPlaybookAliasRescue:
    """Decomposed phases that lost playbook identity should still route to playbooks."""

    @pytest.mark.asyncio
    async def test_exact_playbook_code_in_tool_name_reroutes_to_playbook(self):
        launcher = SimpleNamespace(launch=AsyncMock(return_value={"execution_id": "exec-1"}))
        orch = DispatchOrchestrator(
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

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=items,
        )

        assert result["status"] == "ok"
        launcher.launch.assert_awaited_once()
        assert launcher.launch.await_args.kwargs["playbook_code"] == "page_outline"
        assert phases[0].tool_name is None
        assert phases[0].preferred_engine == "playbook:page_outline"
        assert items[0]["playbook_code"] == "page_outline"
        assert items[0]["tool_name"] is None

    @pytest.mark.asyncio
    async def test_exact_playbook_code_in_tool_name_reroutes_without_cache(self):
        launcher = SimpleNamespace(launch=AsyncMock(return_value={"execution_id": "exec-1b"}))
        orch = DispatchOrchestrator(
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

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=items,
        )

        assert result["status"] == "ok"
        launcher.launch.assert_awaited_once()
        assert launcher.launch.await_args.kwargs["playbook_code"] == "page_outline"
        assert phases[0].tool_name is None
        assert phases[0].preferred_engine == "playbook:page_outline"
        assert items[0]["playbook_code"] == "page_outline"
        assert items[0]["tool_name"] is None

    @pytest.mark.asyncio
    async def test_tool_slot_alias_reroutes_to_structured_playbook(self):
        launcher = SimpleNamespace(launch=AsyncMock(return_value={"execution_id": "exec-2"}))
        orch = DispatchOrchestrator(
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

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=items,
        )

        assert result["status"] == "ok"
        launcher.launch.assert_awaited_once()
        assert launcher.launch.await_args.kwargs["playbook_code"] == "cs_create_schedule"
        assert phases[0].preferred_engine == "playbook:cs_create_schedule"
        assert items[0]["playbook_code"] == "cs_create_schedule"

    @pytest.mark.asyncio
    async def test_tool_slot_alias_reroutes_to_structured_playbook_without_cache(self):
        launcher = SimpleNamespace(launch=AsyncMock(return_value={"execution_id": "exec-2b"}))
        orch = DispatchOrchestrator(
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

        result = await orch.execute(
            task_ir=FakeTaskIR(phases=phases),
            action_items=items,
        )

        assert result["status"] == "ok"
        launcher.launch.assert_awaited_once()
        assert launcher.launch.await_args.kwargs["playbook_code"] == "cs_create_schedule"
        assert phases[0].preferred_engine == "playbook:cs_create_schedule"
        assert items[0]["playbook_code"] == "cs_create_schedule"


class TestAgentDispatch:
    """Agent-preferring phases should route through WorkspaceAgentExecutor."""

    @pytest.mark.asyncio
    async def test_agent_engine_dispatches_to_workspace_runtime_with_inputs(self):
        session = FakeSession(workspace_id="ws-agent")
        orch = DispatchOrchestrator(
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
                    "user_request": "Write the persona operating system and save it to persona_operating_system.md.",
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
                    "user_request": "Write the persona operating system and save it to persona_operating_system.md.",
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
        orch = DispatchOrchestrator(
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
        assert params["user_query"] == "Pick relevant workspace execution Find the best prior workspace execution for evidence reuse"
        assert params["candidates"][0]["execution_id"] == "exec-1"
        assert params["candidates"][0]["playbook_code"] == "ig_generate_personas"
