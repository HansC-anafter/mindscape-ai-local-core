"""
State Management System

Three-layer state model for staged model switching:
- WorldState: Tool results and facts (read-only from tools)
- PlanState: LLM plans (can have multiple versions, can be overwritten)
- DecisionState: Scope/publish/important decisions (only policy can write)

Write rules:
- World: Only tools can write
- Plan: Can be overwritten (by LLM)
- Decision: Only policy can write
"""

from .world_state import WorldState, WorldStateEntry, WorldStateEntryType
from .plan_state import PlanState, PlanVersion, PlanStatus
from .decision_state import DecisionState, DecisionType, DecisionStatus
from .state_manager import StateManager, WriteRule, WriteRuleViolation

__all__ = [
    # WorldState
    "WorldState",
    "WorldStateEntry",
    "WorldStateEntryType",
    # PlanState
    "PlanState",
    "PlanVersion",
    "PlanStatus",
    # DecisionState
    "DecisionState",
    "DecisionType",
    "DecisionStatus",
    # StateManager
    "StateManager",
    "WriteRule",
    "WriteRuleViolation",
    # StateIntegrationAdapter
    "StateIntegrationAdapter",
]

