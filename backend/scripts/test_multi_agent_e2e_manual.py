"""
Multi-Agent End-to-End Manual Test Script

Manual test script for observing multi-agent orchestration behavior.
Can be run interactively to observe agent transitions and loop counting.

Usage:
    python -m backend.scripts.test_multi_agent_e2e_manual
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from backend.app.models.workspace_runtime_profile import (
    TopologyRouting,
    LoopBudget,
    StopConditions
)
from backend.app.services.orchestration.multi_agent_orchestrator import MultiAgentOrchestrator
from backend.app.models.playbook import AgentDefinition
from backend.app.services.orchestration.orchestrator_registry import get_orchestrator_registry


def create_test_agent_roster():
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


def create_test_topology():
    """Create test topology routing"""
    return TopologyRouting(
        default_pattern="sequential",
        agent_routing_rules={
            "researcher": ["writer"],
            "writer": ["reviewer"],
            "reviewer": []
        }
    )


def simulate_execution_flow():
    """Simulate execution flow with agent transitions"""
    print("=" * 60)
    print("Multi-Agent Execution Flow Simulation")
    print("=" * 60)
    print()

    # Create agent roster
    agent_roster = create_test_agent_roster()
    print(f"Agent Roster: {len(agent_roster)} agents")
    for agent_id, agent in agent_roster.items():
        print(f"  - {agent_id}: {agent.agent_name} ({agent.role})")
    print()

    # Create topology
    topology = create_test_topology()
    print(f"Topology: {topology.default_pattern} pattern")
    print(f"Routing Rules:")
    for agent_id, next_agents in topology.agent_routing_rules.items():
        print(f"  {agent_id} -> {next_agents}")
    print()

    # Create orchestrator
    orchestrator = MultiAgentOrchestrator(
        agent_roster=agent_roster,
        topology=topology,
        loop_budget=LoopBudget(
            max_iterations=10,
            max_turns=20,
            max_steps=30,
            max_tool_calls=25
        ),
        stop_conditions=StopConditions(
            definition_of_done=None,
            max_errors=5,
            max_retries=3
        ),
        execution_id="test_exec_manual",
        workspace_id="test-workspace"
    )

    # Register orchestrator
    registry = get_orchestrator_registry()
    registry.register(orchestrator.execution_id, orchestrator)
    print(f"Orchestrator registered: execution_id={orchestrator.execution_id}")
    print()

    try:
        # Get initial agents
        initial_agents = orchestrator.get_next_agents(current_agent_id=None)
        print(f"Initial agents: {initial_agents}")

        if not initial_agents:
            print("No initial agents found!")
            return

        current_agent_id = initial_agents[0]
        orchestrator.set_current_agent(current_agent_id)
        print(f"Starting with agent: {current_agent_id}")
        print()

        # Simulate task execution flow
        task_sequence = [
            ("research", "researcher", ["read_file", "search"]),
            ("write", "writer", ["write_file", "edit_file"]),
            ("review", "reviewer", ["read_file", "lint"])
        ]

        for task_name, expected_agent, tool_calls in task_sequence:
            print("-" * 60)
            print(f"Task: {task_name}")
            print(f"Current agent: {current_agent_id}")
            print(f"Expected agent: {expected_agent}")

            # Check if we should transition
            next_agents = orchestrator.get_next_agents(current_agent_id=current_agent_id)
            print(f"Next agents: {next_agents}")

            if next_agents and current_agent_id != next_agents[0]:
                new_agent_id = next_agents[0]
                orchestrator.set_current_agent(new_agent_id)
                orchestrator.record_turn()
                current_agent_id = new_agent_id
                print(f"Transitioned to agent: {current_agent_id}")
            elif current_agent_id == expected_agent:
                print(f"Already on correct agent: {current_agent_id}")
            else:
                print(f"Agent mismatch: current={current_agent_id}, expected={expected_agent}")

            orchestrator.record_iteration()
            orchestrator.record_step()

            for tool_call in tool_calls:
                orchestrator.record_tool_call()
                print(f"  Tool call: {tool_call}")

            if orchestrator.should_stop():
                print("Stop conditions met!")
                break

            state = orchestrator.state
            print(f"State: iteration={state.iteration_count}, turn={state.turn_count}, "
                  f"step={state.step_count}, tool_call={state.tool_call_count}")
            print()

        print("=" * 60)
        print("Execution Flow Simulation Complete")
        print("=" * 60)
        print()

        state = orchestrator.state
        print("Final State Summary:")
        print(f"  Iterations: {state.iteration_count}")
        print(f"  Turns: {state.turn_count}")
        print(f"  Steps: {state.step_count}")
        print(f"  Tool Calls: {state.tool_call_count}")
        print(f"  Visited Agents: {state.visited_agents}")
        print(f"  Current Agent: {state.current_agent}")
        print()

        print("Verification:")
        assert state.iteration_count == 3, f"Expected 3 iterations, got {state.iteration_count}"
        assert state.turn_count == 2, f"Expected 2 turns, got {state.turn_count}"
        assert state.step_count == 3, f"Expected 3 steps, got {state.step_count}"
        assert state.tool_call_count == 6, f"Expected 6 tool calls, got {state.tool_call_count}"
        assert len(state.visited_agents) == 3, f"Expected 3 visited agents, got {len(state.visited_agents)}"
        print("All expectations met!")

    finally:
        registry.unregister_by_orchestrator(orchestrator)
        print("Cleanup complete")


if __name__ == "__main__":
    simulate_execution_flow()


