"""
State Integration Adapters

Integration adapters to convert existing services to State model:
- ExecutionPlan → PlanState
- Tool results → WorldState
- Policy decisions → DecisionState
"""

import logging
import uuid
from typing import Optional, Dict, Any
from datetime import datetime

from backend.app.models.workspace import ExecutionPlan
from .state_manager import StateManager
from .plan_state import PlanState, PlanVersion, PlanStatus
from .world_state import WorldState, WorldStateEntry, WorldStateEntryType
from .decision_state import DecisionState, DecisionType, DecisionStatus

logger = logging.getLogger(__name__)


class StateIntegrationAdapter:
    """
    State Integration Adapter

    Converts existing service outputs to State model.
    """

    def __init__(self, state_manager: Optional[StateManager] = None):
        """
        Initialize StateIntegrationAdapter

        Args:
            state_manager: StateManager instance (will create if not provided)
        """
        self.state_manager = state_manager or StateManager()

    def execution_plan_to_plan_state(
        self,
        execution_plan: ExecutionPlan,
        model_name: Optional[str] = None,
        reasoning: Optional[str] = None
    ) -> PlanState:
        """
        Convert ExecutionPlan to PlanState

        Args:
            execution_plan: ExecutionPlan instance
            model_name: Model name that created this plan
            reasoning: Reasoning for this plan version

        Returns:
            PlanState instance
        """
        # Create or get PlanState
        state_id = f"plan_{execution_plan.workspace_id}_{execution_plan.id}"
        plan_state = self.state_manager.get_plan_state(state_id)

        if not plan_state:
            plan_state = self.state_manager.create_plan_state(
                state_id=state_id,
                workspace_id=execution_plan.workspace_id,
                plan_id=execution_plan.id,
                metadata={
                    "message_id": execution_plan.message_id,
                    "execution_mode": execution_plan.execution_mode,
                    "project_id": execution_plan.project_id,
                    "phase_id": execution_plan.phase_id,
                }
            )

        # Create PlanVersion from ExecutionPlan
        version_number = len(plan_state.versions) + 1
        version_id = f"{state_id}_v{version_number}"

        plan_version = PlanVersion(
            version_id=version_id,
            version_number=version_number,
            plan_data=execution_plan.dict(),
            created_by=model_name or "unknown",
            reasoning=reasoning or execution_plan.reasoning,
            is_active=True
        )

        # Add version to PlanState
        plan_state.add_version(plan_version, created_by=model_name or "unknown")

        # Update status based on ExecutionPlan
        if execution_plan.confidence and execution_plan.confidence >= 0.8:
            plan_state.status = PlanStatus.ACTIVE
        else:
            plan_state.status = PlanStatus.DRAFT

        return plan_state

    def tool_result_to_world_state(
        self,
        workspace_id: str,
        tool_id: str,
        tool_slot: Optional[str],
        result: Any,
        execution_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> WorldStateEntry:
        """
        Convert tool execution result to WorldStateEntry

        Args:
            workspace_id: Workspace ID
            tool_id: Tool ID that produced the result
            tool_slot: Tool slot (optional)
            result: Tool execution result
            execution_id: Execution ID (optional)
            metadata: Additional metadata

        Returns:
            WorldStateEntry instance
        """
        # Create or get WorldState
        state_id = f"world_{workspace_id}"
        world_state = self.state_manager.get_world_state(state_id)

        if not world_state:
            world_state = self.state_manager.create_world_state(
                state_id=state_id,
                workspace_id=workspace_id,
                metadata={}
            )

        # Create WorldStateEntry
        entry_id = str(uuid.uuid4())
        entry_key = f"{tool_slot or tool_id}_{entry_id[:8]}"

        entry = WorldStateEntry(
            entry_id=entry_id,
            entry_type=WorldStateEntryType.TOOL_RESULT,
            source=f"tool_{tool_id}",
            key=entry_key,
            value=result,
            metadata={
                "tool_id": tool_id,
                "tool_slot": tool_slot,
                "execution_id": execution_id,
                **(metadata or {})
            }
        )

        # Add entry to WorldState (with write rule validation)
        try:
            self.state_manager.write_to_world_state(
                state_id=state_id,
                entry=entry,
                source=f"tool_{tool_id}"
            )
        except Exception as e:
            logger.error(f"Failed to write to WorldState: {e}", exc_info=True)
            raise

        return entry

    def policy_decision_to_decision_state(
        self,
        workspace_id: str,
        decision_id: str,
        decision_type: DecisionType,
        decision_data: Dict[str, Any],
        policy_name: str,
        policy_version: Optional[str] = None,
        reasoning: Optional[str] = None
    ) -> DecisionState:
        """
        Convert policy decision to DecisionState

        Args:
            workspace_id: Workspace ID
            decision_id: Decision ID
            decision_type: Decision type
            decision_data: Decision data
            policy_name: Policy name that made the decision
            policy_version: Policy version (optional)
            reasoning: Policy reasoning (optional)

        Returns:
            DecisionState instance
        """
        # Create or get DecisionState
        state_id = f"decision_{workspace_id}_{decision_id}"
        decision_state = self.state_manager.get_decision_state(state_id)

        if not decision_state:
            decision_state = self.state_manager.create_decision_state(
                state_id=state_id,
                workspace_id=workspace_id,
                decision_id=decision_id,
                decision_type=decision_type,
                decision_data=decision_data,
                policy_name=policy_name,
                metadata={}
            )
        else:
            # Update existing decision
            self.state_manager.write_to_decision_state(
                state_id=state_id,
                decision_data=decision_data,
                policy_name=policy_name,
                reasoning=reasoning,
                policy_version=policy_version
            )
            decision_state = self.state_manager.get_decision_state(state_id)

        return decision_state

    def get_world_state_for_workspace(self, workspace_id: str) -> Optional[WorldState]:
        """Get WorldState for workspace"""
        state_id = f"world_{workspace_id}"
        return self.state_manager.get_world_state(state_id)

    def get_plan_state_for_plan(self, workspace_id: str, plan_id: str) -> Optional[PlanState]:
        """Get PlanState for plan"""
        state_id = f"plan_{workspace_id}_{plan_id}"
        return self.state_manager.get_plan_state(state_id)

    def get_decision_state_for_decision(self, workspace_id: str, decision_id: str) -> Optional[DecisionState]:
        """Get DecisionState for decision"""
        state_id = f"decision_{workspace_id}_{decision_id}"
        return self.state_manager.get_decision_state(state_id)










