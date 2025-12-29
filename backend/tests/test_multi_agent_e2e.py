"""
Multi-Agent End-to-End Test

Tests multi-agent orchestration with agent_roster and topology_routing.
Observes agent transitions, loop counting, and execution flow.
"""

import pytest
import asyncio
from datetime import datetime

from backend.app.models.workspace_runtime_profile import (
    TopologyRouting,
    LoopBudget,
    StopConditions
)
from backend.app.services.orchestration.multi_agent_orchestrator import MultiAgentOrchestrator
from backend.app.models.playbook import AgentDefinition
from backend.app.services.orchestration.orchestrator_registry import get_orchestrator_registry


@pytest.fixture
def test_agent_roster():
    """Create test agent roster"""
    return {
        "researcher": AgentDefinition(
            agent_id="researcher",
            agent_name="Research Agent",
            role="researcher",
            system_prompt="You are a research agent focused on gathering and analyzing information.",
            tools=["read_file", "search", "analyze"],
            memory_scope="workspace",
            responsibility_boundary="Research and information gathering"
        ),
        "writer": AgentDefinition(
            agent_id="writer",
            agent_name="Writing Agent",
            role="writer",
            system_prompt="You are a writing agent focused on creating structured documents.",
            tools=["write_file", "edit_file", "format"],
            memory_scope="workspace",
            responsibility_boundary="Document creation and editing"
        ),
        "reviewer": AgentDefinition(
            agent_id="reviewer",
            agent_name="Review Agent",
            role="reviewer",
            system_prompt="You are a review agent focused on quality assurance.",
            tools=["read_file", "lint", "review"],
            memory_scope="workspace",
            responsibility_boundary="Quality review and validation"
        )
    }


@pytest.fixture
def test_topology():
    """Create test topology routing"""
    return TopologyRouting(
        default_pattern="sequential",
        agent_routing_rules={
            "researcher": ["writer"],
            "writer": ["reviewer"],
            "reviewer": []
        }
    )


def test_initial_agent_selection(test_agent_roster, test_topology):
    """Test initial agent selection"""
    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=test_topology,
        loop_budget=LoopBudget()
    )

    initial_agents = orchestrator.get_next_agents(current_agent_id=None)
    assert len(initial_agents) == 1
    assert initial_agents[0] == "researcher"


def test_agent_transition_flow(test_agent_roster, test_topology):
    """Test agent transition flow"""
    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=test_topology,
        loop_budget=LoopBudget()
    )

    current_agent = None
    next_agents = orchestrator.get_next_agents(current_agent_id=current_agent)
    assert next_agents == ["researcher"]

    current_agent = "researcher"
    next_agents = orchestrator.get_next_agents(current_agent_id=current_agent)
    assert next_agents == ["writer"]

    current_agent = "writer"
    next_agents = orchestrator.get_next_agents(current_agent_id=current_agent)
    assert next_agents == ["reviewer"]

    current_agent = "reviewer"
    next_agents = orchestrator.get_next_agents(current_agent_id=current_agent)
    assert next_agents == []


def test_loop_counting_during_agent_transitions(test_agent_roster, test_topology):
    """Test loop counting during agent transitions"""
    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=test_topology,
        loop_budget=LoopBudget(
            max_iterations=10,
            max_turns=20,
            max_steps=30,
            max_tool_calls=25
        )
    )

    assert orchestrator.state.iteration_count == 0
    assert orchestrator.state.turn_count == 0
    assert orchestrator.state.step_count == 0
    assert orchestrator.state.tool_call_count == 0

    initial_agents = orchestrator.get_next_agents(current_agent_id=None)
    orchestrator.set_current_agent(initial_agents[0])
    orchestrator.record_iteration()
    orchestrator.record_step()
    orchestrator.record_tool_call()

    assert orchestrator.state.iteration_count == 1
    assert orchestrator.state.turn_count == 0
    assert orchestrator.state.step_count == 1
    assert orchestrator.state.tool_call_count == 1

    next_agents = orchestrator.get_next_agents(current_agent_id="researcher")
    orchestrator.set_current_agent(next_agents[0])
    orchestrator.record_turn()
    orchestrator.record_iteration()
    orchestrator.record_step()
    orchestrator.record_tool_call()

    assert orchestrator.state.iteration_count == 2
    assert orchestrator.state.turn_count == 1
    assert orchestrator.state.step_count == 2
    assert orchestrator.state.tool_call_count == 2

    next_agents = orchestrator.get_next_agents(current_agent_id="writer")
    orchestrator.set_current_agent(next_agents[0])
    orchestrator.record_turn()
    orchestrator.record_iteration()
    orchestrator.record_step()
    orchestrator.record_tool_call()

    assert orchestrator.state.iteration_count == 3
    assert orchestrator.state.turn_count == 2
    assert orchestrator.state.step_count == 3
    assert orchestrator.state.tool_call_count == 3


def test_loop_budget_stop_condition(test_agent_roster, test_topology):
    """Test loop budget stop condition"""
    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=test_topology,
        loop_budget=LoopBudget(
            max_iterations=2,
            max_turns=3,
            max_steps=4,
            max_tool_calls=5
        )
    )

    assert orchestrator.should_stop() is False

    orchestrator.record_iteration()
    assert orchestrator.should_stop() is False

    orchestrator.record_iteration()
    assert orchestrator.should_stop() is True


def test_visited_agents_tracking(test_agent_roster, test_topology):
    """Test visited agents tracking"""
    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=test_topology,
        loop_budget=LoopBudget()
    )

    orchestrator.set_current_agent("researcher")
    assert "researcher" in orchestrator.state.visited_agents

    orchestrator.set_current_agent("writer")
    assert "writer" in orchestrator.state.visited_agents
    assert len(orchestrator.state.visited_agents) == 2

    orchestrator.set_current_agent("reviewer")
    assert "reviewer" in orchestrator.state.visited_agents
    assert len(orchestrator.state.visited_agents) == 3


def test_end_to_end_execution_flow(test_agent_roster, test_topology):
    """Test end-to-end execution flow"""
    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=test_topology,
        loop_budget=LoopBudget(
            max_iterations=10,
            max_turns=20,
            max_steps=30,
            max_tool_calls=25
        )
    )

    # Register orchestrator
    registry = get_orchestrator_registry()
    execution_id = f"test_exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    registry.register(execution_id, orchestrator)

    try:
        current_agent_id = None
        task_sequence = ["researcher", "writer", "reviewer"]

        for expected_agent in task_sequence:
            next_agents = orchestrator.get_next_agents(current_agent_id=current_agent_id)

            if next_agents:
                new_agent_id = next_agents[0]
                if current_agent_id != new_agent_id:
                    orchestrator.set_current_agent(new_agent_id)
                    if current_agent_id is not None:
                        orchestrator.record_turn()
                    current_agent_id = new_agent_id

                orchestrator.record_iteration()
                orchestrator.record_step()
                orchestrator.record_tool_call()
                orchestrator.record_tool_call()

                if orchestrator.should_stop():
                    break

        state = orchestrator.state
        assert state.iteration_count == 3
        assert state.turn_count == 2
        assert state.step_count == 3
        assert state.tool_call_count == 6
        assert len(state.visited_agents) == 3

    finally:
        registry.unregister_by_orchestrator(orchestrator)


def test_orchestrator_registry_integration(test_agent_roster, test_topology):
    """Test orchestrator registry integration"""
    registry = get_orchestrator_registry()
    registry.clear()

    try:
        orchestrator = MultiAgentOrchestrator(
            agent_roster=test_agent_roster,
            topology=test_topology,
            loop_budget=LoopBudget()
        )

        execution_id = "test_exec_123"
        registry.register(execution_id, orchestrator)

        retrieved = registry.get(execution_id)
        assert retrieved is orchestrator

        orchestrator.record_tool_call()
        assert orchestrator.state.tool_call_count == 1

        registry.unregister_by_orchestrator(orchestrator)
        assert registry.get(execution_id) is None

    finally:
        registry.clear()


def test_topology_pattern_sequential(test_agent_roster):
    """Test sequential topology pattern"""
    topology = TopologyRouting(
        default_pattern="sequential",
        agent_routing_rules={
            "researcher": ["writer"],
            "writer": ["reviewer"],
            "reviewer": []
        }
    )

    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=topology,
        loop_budget=LoopBudget()
    )

    assert orchestrator.get_next_agents(None) == ["researcher"]
    assert orchestrator.get_next_agents("researcher") == ["writer"]
    assert orchestrator.get_next_agents("writer") == ["reviewer"]
    assert orchestrator.get_next_agents("reviewer") == []


def test_topology_pattern_loop(test_agent_roster):
    """Test loop topology pattern"""
    topology = TopologyRouting(
        default_pattern="loop",
        agent_routing_rules={
            "researcher": ["writer"],
            "writer": ["reviewer"],
            "reviewer": ["researcher"]  # Loop back
        }
    )

    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=topology,
        loop_budget=LoopBudget(max_iterations=5)
    )

    assert orchestrator.get_next_agents(None) == ["researcher"]
    assert orchestrator.get_next_agents("researcher") == ["writer"]
    assert orchestrator.get_next_agents("writer") == ["reviewer"]
    assert orchestrator.get_next_agents("reviewer") == ["researcher"]

    orchestrator.set_current_agent("researcher")
    orchestrator.record_iteration()
    assert orchestrator.state.iteration_count == 1

    orchestrator.set_current_agent("writer")
    orchestrator.record_turn()
    orchestrator.set_current_agent("reviewer")
    orchestrator.record_turn()
    orchestrator.set_current_agent("researcher")
    orchestrator.record_turn()
    orchestrator.record_iteration()
    assert orchestrator.state.iteration_count == 2


def test_multiple_tool_calls_per_agent(test_agent_roster, test_topology):
    """Test multiple tool calls per agent"""
    orchestrator = MultiAgentOrchestrator(
        agent_roster=test_agent_roster,
        topology=test_topology,
        loop_budget=LoopBudget(max_tool_calls=10)
    )

    orchestrator.set_current_agent("researcher")

    for _ in range(5):
        orchestrator.record_tool_call()

    assert orchestrator.state.tool_call_count == 5
    assert orchestrator.should_stop() is False

    for _ in range(5):
        orchestrator.record_tool_call()

    assert orchestrator.state.tool_call_count == 10
    assert orchestrator.should_stop() is True

