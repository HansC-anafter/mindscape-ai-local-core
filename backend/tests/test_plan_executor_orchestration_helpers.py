from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from backend.app.models.playbook import AgentDefinition
from backend.app.models.workspace_runtime_profile import (
    LoopBudget,
    TopologyRouting,
    WorkspaceRuntimeProfile,
)
from backend.app.services.conversation.plan_executor_core import (
    advance_execution_orchestration,
    cleanup_execution_orchestration,
    initialize_execution_orchestration,
    register_execution_with_orchestrator,
)
from backend.app.services.orchestration.orchestrator_registry import (
    get_orchestrator_registry,
)


@pytest.fixture
def clean_registry():
    registry = get_orchestrator_registry()
    registry.clear()
    yield registry
    registry.clear()


@pytest.fixture
def sample_agent_roster():
    return {
        "researcher": AgentDefinition(
            agent_id="researcher",
            agent_name="Research Agent",
            role="researcher",
        ),
        "writer": AgentDefinition(
            agent_id="writer",
            agent_name="Writer Agent",
            role="writer",
        ),
    }


@pytest.fixture
def sample_runtime_profile():
    return WorkspaceRuntimeProfile(
        topology_routing=TopologyRouting(
            agent_routing_rules={"researcher": ["writer"]},
            default_pattern="sequential",
        ),
        loop_budget=LoopBudget(max_tool_calls=3),
    )


@pytest.mark.asyncio
async def test_initialize_execution_orchestration_bootstraps_initial_agent(
    clean_registry,
    sample_agent_roster,
    sample_runtime_profile,
):
    execution_plan = SimpleNamespace(tasks=[SimpleNamespace(pack_id="pack.alpha")])
    workspace = SimpleNamespace(id="ws_123")
    ctx = SimpleNamespace()
    resolve_playbook = AsyncMock(
        return_value=SimpleNamespace(
            playbook=SimpleNamespace(agent_roster=sample_agent_roster)
        )
    )

    state = await initialize_execution_orchestration(
        execution_plan=execution_plan,
        ctx=ctx,
        workspace=workspace,
        runtime_profile=sample_runtime_profile,
        stop_conditions=sample_runtime_profile.stop_conditions,
        message_id="msg_123",
        resolve_playbook=resolve_playbook,
        event_store_factory=lambda: Mock(),
    )

    assert state.orchestrator is not None
    assert state.current_agent_id is None
    assert state.orchestrator.state.current_agent == "researcher"
    assert state.registered_execution_ids == ["msg_123"]
    assert clean_registry.get("msg_123") is state.orchestrator


@pytest.mark.asyncio
async def test_execution_orchestration_advances_and_cleans_up(
    clean_registry,
    sample_agent_roster,
    sample_runtime_profile,
):
    execution_plan = SimpleNamespace(
        tasks=[
            SimpleNamespace(pack_id="pack.alpha"),
            SimpleNamespace(pack_id="pack.beta"),
        ]
    )
    resolve_playbook = AsyncMock(
        return_value=SimpleNamespace(
            playbook=SimpleNamespace(agent_roster=sample_agent_roster)
        )
    )

    state = await initialize_execution_orchestration(
        execution_plan=execution_plan,
        ctx=SimpleNamespace(),
        workspace=SimpleNamespace(id="ws_123"),
        runtime_profile=sample_runtime_profile,
        stop_conditions=sample_runtime_profile.stop_conditions,
        message_id="msg_123",
        resolve_playbook=resolve_playbook,
        event_store_factory=lambda: Mock(),
    )

    assert advance_execution_orchestration(state, 1) is True
    assert state.current_agent_id == "researcher"
    assert state.orchestrator.state.turn_count == 1

    assert advance_execution_orchestration(state, 2) is True
    assert state.current_agent_id == "writer"
    assert state.orchestrator.state.turn_count == 2

    register_execution_with_orchestrator(state, "exec_123", "msg_123")
    assert state.primary_execution_id == "exec_123"
    assert clean_registry.get("exec_123") is state.orchestrator
    assert clean_registry.get("msg_123") is state.orchestrator

    cleanup_execution_orchestration(state)
    assert clean_registry.get("exec_123") is None
    assert clean_registry.get("msg_123") is None
