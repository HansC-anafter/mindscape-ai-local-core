"""Typed planner tool-plan models for MeetingEngine execution."""

from __future__ import annotations

from typing import Any, Dict, List

from pydantic import BaseModel, Field


class PlannerToolPlanCategory(BaseModel):
    """One deterministic grouping target in a planner tool plan."""

    category_id: str = Field(..., description="Stable category identifier")
    label: str = Field(..., description="Human-readable category label")
    description: str = Field(default="", description="Creative-space description")
    idempotency_key: str = Field(..., description="Stable retry key for write tools")


class PlannerToolPlanStep(BaseModel):
    """One executable planner-contract tool call."""

    step_id: str = Field(..., description="Plan-local stable step identifier")
    role: str = Field(..., description="Plan role such as query_references")
    category_id: str = Field(..., description="PlannerToolPlanCategory.category_id")
    category_label: str = Field(..., description="Copied label for graph/debug output")
    tool_name: str = Field(..., description="Canonical tool name, e.g. ig.tool_code")
    resource_kind: str = Field(..., description="planner_contract.resource_kind")
    effect: str = Field(..., description="planner_contract.effect")
    arguments: Dict[str, Any] = Field(default_factory=dict)
    input_bindings: Dict[str, Any] = Field(default_factory=dict)
    result_selectors: Dict[str, str] = Field(default_factory=dict)
    max_selector_fanout: int = Field(default=200, ge=1, le=500)
    depends_on: List[str] = Field(default_factory=list)
    planner_contract: Dict[str, Any] = Field(default_factory=dict)


class PlannerToolPlan(BaseModel):
    """Meeting-level deterministic tool plan executed by one core tool."""

    schema_version: str = "meeting.planner_tool_plan.v1"
    plan_id: str = Field(..., description="Stable plan identifier")
    workspace_id: str = Field(..., description="Workspace that owns the data")
    meeting_id: str = Field(..., description="Meeting session id")
    pack_id: str = Field(..., description="Active capability pack id")
    categories: List[PlannerToolPlanCategory] = Field(default_factory=list)
    steps: List[PlannerToolPlanStep] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def as_execution_payload(self) -> Dict[str, Any]:
        """Return JSON-safe payload for PhaseIR.input_params."""
        return self.model_dump(mode="json", exclude_none=True)
