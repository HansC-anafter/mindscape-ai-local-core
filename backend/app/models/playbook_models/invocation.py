"""Invocation context and strategy models for playbooks."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .enums import InvocationMode, InvocationTolerance


class InvocationStrategy(BaseModel):
    """Invocation strategy for playbook execution."""

    max_lookup_rounds: int = Field(
        default=3,
        description="Maximum lookup rounds for data gathering (standalone mode)",
    )
    allow_spawn_new_tasks: bool = Field(
        default=False, description="Whether this playbook can spawn new tasks"
    )
    allow_expansion: bool = Field(
        default=False,
        description="Whether this playbook can expand (create new scripts)",
    )
    wait_for_upstream_tasks: bool = Field(
        default=True,
        description="Whether to wait for upstream tasks in plan mode",
    )
    tolerance: InvocationTolerance = Field(
        default=InvocationTolerance.STRICT,
        description="Tolerance level when data is insufficient",
    )


class PlanContext(BaseModel):
    """Plan context for plan_node mode."""

    plan_summary: str = Field(..., description="Plan summary")
    reasoning: str = Field(..., description="Plan reasoning")
    steps: List[Dict[str, Any]] = Field(
        default_factory=list, description="Execution steps"
    )
    dependencies: List[str] = Field(
        default_factory=list, description="Dependencies: list of task IDs"
    )


class PlaybookInvocationContext(BaseModel):
    """Playbook invocation context."""

    mode: InvocationMode = Field(
        ..., description="Execution mode: standalone, plan_node, or subroutine"
    )
    project_id: Optional[str] = Field(None, description="Project ID")
    phase_id: Optional[str] = Field(None, description="Project phase ID")
    plan_id: Optional[str] = Field(None, description="Plan ID (plan_node mode)")
    task_id: Optional[str] = Field(None, description="Task ID (plan_node mode)")
    plan_context: Optional[PlanContext] = Field(
        None, description="Plan context (plan_node mode)"
    )
    visible_state: Optional[Dict[str, Any]] = Field(
        None,
        description="Visible state snapshot for this invocation",
    )
    strategy: InvocationStrategy = Field(
        default_factory=InvocationStrategy,
        description="Invocation strategy",
    )
    trace_id: str = Field(
        ..., description="Global trace ID for this user request/execution"
    )
    parent_run_id: Optional[str] = Field(
        None, description="Parent run ID (subroutine mode)"
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

