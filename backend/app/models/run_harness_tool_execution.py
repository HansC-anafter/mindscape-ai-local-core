"""Request contract for workspace-scoped run harness tool execution."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import Field

from backend.app.models.run_harness import (
    RunIntentEnvelope,
    SideEffectClass,
    StrictModel,
    ToolAdmissionPolicy,
)


class RunHarnessToolExecutionRequest(StrictModel):
    run_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    envelope: RunIntentEnvelope
    tool_ref: str = Field(min_length=1)
    arguments: Dict[str, Any] = Field(default_factory=dict)
    side_effect: SideEffectClass = SideEffectClass.READONLY
    policy: ToolAdmissionPolicy
    approval_granted: bool = False
    rollback_available: bool = False
    product_surface_id: Optional[str] = Field(default=None, min_length=2)
    active_group_id: Optional[str] = Field(default=None, min_length=1)
    observed_topology_revision: Optional[int] = Field(default=None, ge=1)
    execution_backend: Literal["local", "remote", "external_provider"] = "local"
