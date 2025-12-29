"""
Multi-Agent Orchestrator

Orchestrates multi-agent workflows based on topology routing and agent roster.
Supports sequential, loop, parallel, and hierarchical patterns.
"""

from typing import Dict, List, Optional, Any
from datetime import datetime
import uuid
from backend.app.models.playbook import AgentDefinition
from backend.app.models.workspace_runtime_profile import (
    TopologyRouting,
    LoopBudget,
    StopConditions
)
from backend.app.services.orchestration.topology_validator import (
    TopologyValidator,
    TopologyValidationError
)
from backend.app.models.mindscape import MindEvent, EventType, EventActor
import logging

logger = logging.getLogger(__name__)


class OrchestrationState:
    """State tracking for multi-agent orchestration"""

    def __init__(self):
        self.current_agent: Optional[str] = None
        self.iteration_count: int = 0
        self.turn_count: int = 0
        self.step_count: int = 0
        self.tool_call_count: int = 0
        self.error_count: int = 0
        self.retry_count: int = 0
        self.visited_agents: List[str] = []
        self.agent_results: Dict[str, Any] = {}
        self.start_time: datetime = datetime.utcnow()

    def can_continue(self, loop_budget: Optional[LoopBudget], stop_conditions: Optional[StopConditions]) -> bool:
        """
        Check if orchestration can continue based on budgets and stop conditions

        Args:
            loop_budget: Loop budget configuration
            stop_conditions: Stop conditions configuration

        Returns:
            True if can continue, False otherwise
        """
        if loop_budget:
            if self.iteration_count >= loop_budget.max_iterations:
                logger.info(f"Stopped: max_iterations ({loop_budget.max_iterations}) reached")
                return False
            if self.turn_count >= loop_budget.max_turns:
                logger.info(f"Stopped: max_turns ({loop_budget.max_turns}) reached")
                return False
            if self.step_count >= loop_budget.max_steps:
                logger.info(f"Stopped: max_steps ({loop_budget.max_steps}) reached")
                return False
            if self.tool_call_count >= loop_budget.max_tool_calls:
                logger.info(f"Stopped: max_tool_calls ({loop_budget.max_tool_calls}) reached")
                return False

        if stop_conditions:
            if self.error_count >= stop_conditions.max_errors:
                logger.info(f"Stopped: max_errors ({stop_conditions.max_errors}) reached")
                return False
            if self.retry_count >= stop_conditions.max_retries:
                logger.info(f"Stopped: max_retries ({stop_conditions.max_retries}) reached")
                return False

        return True


class MultiAgentOrchestrator:
    """
    Multi-Agent Orchestrator - 多 Agent 協作

    Orchestrates multi-agent workflows based on:
    - Agent Roster (from Playbook): Who can do what
    - Topology Routing (from Runtime Profile): How agents pass the ball
    - Loop Budget (from Runtime Profile): Iteration limits
    - Stop Conditions (from Runtime Profile): Completion criteria
    """

    def __init__(
        self,
        agent_roster: Dict[str, AgentDefinition],
        topology: TopologyRouting,
        loop_budget: Optional[LoopBudget] = None,
        stop_conditions: Optional[StopConditions] = None,
        execution_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        event_store: Optional[Any] = None
    ):
        """
        Initialize Multi-Agent Orchestrator

        Args:
            agent_roster: Agent roster from playbook
            topology: Topology routing from runtime profile
            loop_budget: Loop budget configuration
            stop_conditions: Stop conditions configuration
            execution_id: Execution ID (for event recording)
            workspace_id: Workspace ID (for event recording)
            profile_id: Profile ID (for event recording)
            event_store: Optional event store for recording events
        """
        self.agent_roster = agent_roster
        self.topology = topology
        self.loop_budget = loop_budget
        self.stop_conditions = stop_conditions
        self.execution_id = execution_id
        self.workspace_id = workspace_id
        self.profile_id = profile_id
        self.event_store = event_store
        self._budget_exhausted_event_recorded = False  # Track if event already recorded

        # Validate topology against agent roster
        validator = TopologyValidator()
        try:
            validator.validate(topology, agent_roster)
        except TopologyValidationError as e:
            raise ValueError(f"Invalid topology configuration: {e}")

        # Initialize state
        self.state = OrchestrationState()

    def get_next_agents(self, current_agent_id: Optional[str] = None) -> List[str]:
        """
        Get next agents based on topology routing

        Args:
            current_agent_id: Current agent ID (None for initial agent)

        Returns:
            List of next agent IDs
        """
        if current_agent_id is None:
            # Determine initial agent based on pattern
            if self.topology.default_pattern == "hierarchical":
                root_agent = self.topology.pattern_config.get("root_agent")
                if root_agent and root_agent in self.agent_roster:
                    return [root_agent]
            # Default: return first agent in roster
            if self.agent_roster:
                return [list(self.agent_roster.keys())[0]]
            return []

        # Get next agents from routing rules
        next_agents = self.topology.agent_routing_rules.get(current_agent_id, [])
        return next_agents

    def should_stop(self) -> bool:
        """
        Check if orchestration should stop

        Returns:
            True if should stop, False otherwise
        """
        can_continue = self.state.can_continue(self.loop_budget, self.stop_conditions)
        should_stop = not can_continue

        # Record budget exhausted event (P1: Observability)
        if should_stop and not self._budget_exhausted_event_recorded:
            self._record_budget_exhausted_event()
            self._budget_exhausted_event_recorded = True

        return should_stop

    def _record_budget_exhausted_event(self):
        """
        Record loop budget exhausted event for observability (P1)

        Records which budget limit was reached and current state values.
        """
        if not self.event_store or not self.execution_id:
            # Skip event recording if event_store or execution_id not provided
            return

        try:
            # Determine which limit was reached
            exhausted_limits = []
            if self.loop_budget:
                if self.state.iteration_count >= self.loop_budget.max_iterations:
                    exhausted_limits.append("max_iterations")
                if self.state.turn_count >= self.loop_budget.max_turns:
                    exhausted_limits.append("max_turns")
                if self.state.step_count >= self.loop_budget.max_steps:
                    exhausted_limits.append("max_steps")
                if self.state.tool_call_count >= self.loop_budget.max_tool_calls:
                    exhausted_limits.append("max_tool_calls")

            if self.stop_conditions:
                if self.state.error_count >= self.stop_conditions.max_errors:
                    exhausted_limits.append("max_errors")
                if self.state.retry_count >= self.stop_conditions.max_retries:
                    exhausted_limits.append("max_retries")

            if exhausted_limits:
                event = MindEvent(
                    id=str(uuid.uuid4()),
                    timestamp=datetime.utcnow(),
                    actor=EventActor.SYSTEM,
                    channel="runtime_profile",
                    profile_id=self.profile_id or "system",
                    workspace_id=self.workspace_id,
                    event_type=EventType.LOOP_BUDGET_EXHAUSTED,
                    payload={
                        "execution_id": self.execution_id,
                        "exhausted_limits": exhausted_limits,
                        "current_state": {
                            "iteration_count": self.state.iteration_count,
                            "turn_count": self.state.turn_count,
                            "step_count": self.state.step_count,
                            "tool_call_count": self.state.tool_call_count,
                            "error_count": self.state.error_count,
                            "retry_count": self.state.retry_count
                        },
                        "budget_limits": {
                            "max_iterations": self.loop_budget.max_iterations if self.loop_budget else None,
                            "max_turns": self.loop_budget.max_turns if self.loop_budget else None,
                            "max_steps": self.loop_budget.max_steps if self.loop_budget else None,
                            "max_tool_calls": self.loop_budget.max_tool_calls if self.loop_budget else None,
                            "max_errors": self.stop_conditions.max_errors if self.stop_conditions else None,
                            "max_retries": self.stop_conditions.max_retries if self.stop_conditions else None
                        }
                    }
                )
                self.event_store.create(event)
                logger.info(
                    f"MultiAgentOrchestrator: Recorded budget exhausted event for execution_id={self.execution_id}, "
                    f"exhausted_limits={exhausted_limits}"
                )
        except Exception as e:
            # Don't fail orchestration if event recording fails
            logger.warning(f"Failed to record budget exhausted event: {e}", exc_info=True)

    def record_iteration(self):
        """Record an iteration"""
        self.state.iteration_count += 1

    def record_turn(self):
        """Record a conversation turn"""
        self.state.turn_count += 1

    def record_step(self):
        """Record an execution step"""
        self.state.step_count += 1

    def record_tool_call(self):
        """Record a tool call"""
        self.state.tool_call_count += 1

    def record_error(self):
        """Record an error"""
        self.state.error_count += 1

    def record_retry(self):
        """Record a retry"""
        self.state.retry_count += 1

    def set_current_agent(self, agent_id: str):
        """Set current agent"""
        self.state.current_agent = agent_id
        if agent_id not in self.state.visited_agents:
            self.state.visited_agents.append(agent_id)

    def set_agent_result(self, agent_id: str, result: Any):
        """Set result for an agent"""
        self.state.agent_results[agent_id] = result

    def get_state(self) -> OrchestrationState:
        """Get current orchestration state"""
        return self.state

    def get_agent_definition(self, agent_id: str) -> Optional[AgentDefinition]:
        """Get agent definition by ID"""
        return self.agent_roster.get(agent_id)

