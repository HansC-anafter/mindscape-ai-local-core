"""
State Manager

Manages three-layer state model with write rules:
- World: Only tools can write
- Plan: Can be overwritten (by LLM)
- Decision: Only policy can write
"""

from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum

from .world_state import WorldState, WorldStateEntry
from .plan_state import PlanState, PlanVersion
from .decision_state import DecisionState


class WriteRule(str, Enum):
    """Write rule"""
    WORLD_TOOL_ONLY = "world_tool_only"  # World can only be written by tools
    PLAN_LLM_OVERWRITE = "plan_llm_overwrite"  # Plan can be overwritten by LLM
    DECISION_POLICY_ONLY = "decision_policy_only"  # Decision can only be written by policy


@dataclass
class WriteRuleViolation(Exception):
    """Write rule violation exception"""
    rule: WriteRule
    state_type: str
    source: str
    message: str

    def __str__(self) -> str:
        return f"Write rule violation: {self.rule.value} - {self.message} (state_type={self.state_type}, source={self.source})"


class StateManager:
    """
    State Manager

    Manages three-layer state model with write rules validation.
    """

    def __init__(self):
        """Initialize StateManager"""
        self._world_states: Dict[str, WorldState] = {}
        self._plan_states: Dict[str, PlanState] = {}
        self._decision_states: Dict[str, DecisionState] = {}

    def get_world_state(self, state_id: str) -> Optional[WorldState]:
        """Get WorldState by ID"""
        return self._world_states.get(state_id)

    def get_plan_state(self, state_id: str) -> Optional[PlanState]:
        """Get PlanState by ID"""
        return self._plan_states.get(state_id)

    def get_decision_state(self, state_id: str) -> Optional[DecisionState]:
        """Get DecisionState by ID"""
        return self._decision_states.get(state_id)

    def create_world_state(self, state_id: str, workspace_id: str, metadata: Optional[Dict[str, Any]] = None) -> WorldState:
        """Create a new WorldState"""
        state = WorldState(
            state_id=state_id,
            workspace_id=workspace_id,
            metadata=metadata or {}
        )
        self._world_states[state_id] = state
        return state

    def create_plan_state(self, state_id: str, workspace_id: str, plan_id: str, metadata: Optional[Dict[str, Any]] = None) -> PlanState:
        """Create a new PlanState"""
        state = PlanState(
            state_id=state_id,
            workspace_id=workspace_id,
            plan_id=plan_id,
            metadata=metadata or {}
        )
        self._plan_states[state_id] = state
        return state

    def create_decision_state(
        self,
        state_id: str,
        workspace_id: str,
        decision_id: str,
        decision_type: str,
        decision_data: Dict[str, Any],
        policy_name: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> DecisionState:
        """Create a new DecisionState"""
        from .decision_state import DecisionType

        state = DecisionState(
            state_id=state_id,
            workspace_id=workspace_id,
            decision_id=decision_id,
            decision_type=DecisionType(decision_type),
            decision_data=decision_data,
            policy_name=policy_name,
            metadata=metadata or {}
        )
        self._decision_states[state_id] = state
        return state

    def write_to_world_state(
        self,
        state_id: str,
        entry: WorldStateEntry,
        source: str
    ) -> WorldState:
        """
        Write to WorldState (with write rule validation)

        Args:
            state_id: WorldState ID
            entry: WorldStateEntry to add
            source: Source identifier (must be a tool source)

        Returns:
            Updated WorldState

        Raises:
            WriteRuleViolation: If write rule is violated
        """
        # Validate write rule: World can only be written by tools
        if not source.startswith("tool_") and not source.startswith("execution_"):
            raise WriteRuleViolation(
                rule=WriteRule.WORLD_TOOL_ONLY,
                state_type="world",
                source=source,
                message=f"WorldState can only be written by tools. Invalid source: {source}"
            )

        state = self.get_world_state(state_id)
        if not state:
            raise ValueError(f"WorldState not found: {state_id}")

        state.add_entry(entry, source)
        return state

    def write_to_plan_state(
        self,
        state_id: str,
        plan_version: PlanVersion,
        created_by: str
    ) -> PlanState:
        """
        Write to PlanState (with write rule validation)

        Args:
            state_id: PlanState ID
            plan_version: PlanVersion to add
            created_by: Creator identifier (model_name, user_id, etc.)

        Returns:
            Updated PlanState

        Note:
            PlanState can be written by LLM (no strict validation, but log if not LLM)
        """
        state = self.get_plan_state(state_id)
        if not state:
            raise ValueError(f"PlanState not found: {state_id}")

        state.add_version(plan_version, created_by)
        return state

    def write_to_decision_state(
        self,
        state_id: str,
        decision_data: Dict[str, Any],
        policy_name: str,
        reasoning: Optional[str] = None,
        policy_version: Optional[str] = None
    ) -> DecisionState:
        """
        Write to DecisionState (with write rule validation)

        Args:
            state_id: DecisionState ID
            decision_data: Updated decision data
            policy_name: Policy name making the update
            reasoning: Policy reasoning
            policy_version: Policy version

        Returns:
            Updated DecisionState

        Raises:
            WriteRuleViolation: If write rule is violated
        """
        # Validate write rule: Decision can only be written by policy
        if not policy_name.startswith("policy_"):
            raise WriteRuleViolation(
                rule=WriteRule.DECISION_POLICY_ONLY,
                state_type="decision",
                source=policy_name,
                message=f"DecisionState can only be written by policy. Invalid policy_name: {policy_name}"
            )

        state = self.get_decision_state(state_id)
        if not state:
            raise ValueError(f"DecisionState not found: {state_id}")

        state.update_decision(decision_data, policy_name, reasoning, policy_version)
        return state

    def validate_write_rule(
        self,
        state_type: str,
        source: str
    ) -> bool:
        """
        Validate write rule

        Args:
            state_type: State type ("world", "plan", "decision")
            source: Source identifier

        Returns:
            True if write rule is valid, False otherwise
        """
        if state_type == "world":
            return source.startswith("tool_") or source.startswith("execution_")
        elif state_type == "plan":
            # Plan can be written by LLM (no strict validation)
            return True
        elif state_type == "decision":
            return source.startswith("policy_")
        else:
            return False





