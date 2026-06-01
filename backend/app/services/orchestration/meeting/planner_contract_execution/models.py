"""Typed planner contract binding models."""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PlannerContractEffect(str, Enum):
    """Supported planner contract effects."""

    READ = "read"
    WRITE = "write"
    ACTION = "action"
    DELETE = "delete"


class PlannerContractBindingError(Exception):
    """Raised when a planner data operation cannot be safely bound."""


class PlannerDataOperation(BaseModel):
    """Normalized data operation intent used by the binding service."""

    id: str = Field(..., description="Contract-scoped operation ID")
    resource_kind: str = Field(..., description="Planner resource kind")
    effect: PlannerContractEffect = Field(..., description="Requested effect")
    tool_name: Optional[str] = Field(default=None, description="Requested tool name")
    query: Dict[str, Any] = Field(default_factory=dict, description="Operation payload")
    target_object_kind: Optional[str] = Field(default=None)
    acceptance_condition: Optional[str] = Field(default=None)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class PlannerContractBinding(BaseModel):
    """Deterministic binding between a PhaseIR tool call and manifest contract."""

    binding_id: str = Field(..., description="Stable binding ID")
    data_operation_id: Optional[str] = Field(
        default=None, description="RequestContract data operation ID"
    )
    pack_id: str = Field(..., description="Installed capability pack")
    tool_name: str = Field(..., description="Canonical tool name pack.tool")
    tool_code: str = Field(..., description="Manifest tool code")
    resource_kind: str = Field(..., description="Planner resource kind")
    effect: PlannerContractEffect = Field(..., description="Planner effect")
    workspace_scoped: bool = Field(default=True)
    input_schema: Optional[str] = Field(default=None)
    output_schema: Optional[str] = Field(default=None)
    pagination: Optional[Dict[str, Any]] = Field(default=None)
    idempotency: Optional[str] = Field(default=None)
    approval_required: bool = Field(default=False)
    audit_fields: List[str] = Field(default_factory=list)
    source: str = Field(default="installed_manifest")
    contract: Dict[str, Any] = Field(default_factory=dict)

    def as_execution_context(self) -> Dict[str, Any]:
        """Return a JSON-serializable payload for Task metadata."""
        return self.model_dump(mode="json", exclude_none=True)
