"""Request contract for workspace-scoped run harness workflow execution."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import Field

from backend.app.models.run_harness import RunIntentEnvelope, StrictModel


class RunHarnessWorkflowExecutionRequest(StrictModel):
    run_id: str = Field(min_length=1)
    episode_id: str = Field(min_length=1)
    envelope: RunIntentEnvelope
    playbook_code: str = Field(min_length=1)
    normalized_inputs: Dict[str, Any] = Field(default_factory=dict)
    workspace_id: str = Field(min_length=1)
    project_id: Optional[str] = None
    profile_id: str = Field(min_length=1)
    execution_backend: str = "auto"
    product_surface_id: Optional[str] = Field(default=None, min_length=2)
    active_group_id: Optional[str] = Field(default=None, min_length=1)
    observed_topology_revision: Optional[int] = Field(default=None, ge=1)
