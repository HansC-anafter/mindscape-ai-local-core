"""playbook.json schema models."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .enums import PlaybookKind


class PlaybookInput(BaseModel):
    """Input definition for playbook.json."""

    type: str = Field(
        ..., description="Input type (e.g., string, list[string], integer)"
    )
    required: bool = Field(default=True, description="Whether this input is required")
    default: Optional[Any] = Field(None, description="Default value if not provided")
    description: Optional[str] = Field(None, description="Input description")


class PlaybookOutput(BaseModel):
    """Output definition for playbook.json."""

    type: str = Field(..., description="Output type (e.g., string, list[object])")
    description: Optional[str] = Field(None, description="Output description")
    source: str = Field(..., description="Source path (e.g., step.ocr.ocr_text)")


class ToolPolicy(BaseModel):
    """Tool execution policy constraints."""

    risk_level: Literal["read", "write"] = Field(
        default="read", description="Risk level: read-only or write operations"
    )
    env: Literal["sandbox_only", "allow_prod"] = Field(
        default="sandbox_only",
        description="Environment constraint: sandbox only or allow production",
    )
    requires_preview: bool = Field(
        default=True,
        description="Whether write operations require preview before execution",
    )
    allowed_slots: Optional[List[str]] = Field(
        None, description="List of allowed tool slots (alternative to tool_slot field)"
    )
    allowed_tool_patterns: Optional[List[str]] = Field(
        None,
        description="Allowed tool ID patterns (e.g., wp-*.wordpress.*, canva-*.canva.*)",
    )


class GateSpec(BaseModel):
    """Gate specification for a playbook step."""

    required: bool = Field(
        default=False, description="Whether this step requires human approval"
    )
    type: Literal["validation", "modification"] = Field(
        default="validation", description="Gate type"
    )
    operation: Optional[str] = Field(
        default=None, description="Operation name (e.g., batch_update, publish)"
    )
    checkpoint_required: Optional[bool] = Field(
        default=None,
        description="Whether checkpoint is required for rollback",
    )


class PlaybookStep(BaseModel):
    """Step definition in playbook.json."""

    id: str = Field(..., description="Step unique identifier")
    tool: Optional[str] = Field(
        None,
        description="Concrete tool ID to call (legacy). Use tool_slot for new playbooks.",
    )
    tool_slot: Optional[str] = Field(
        None,
        description="Logical tool slot identifier resolved to tool_id at runtime.",
    )
    tool_policy: Optional[ToolPolicy] = Field(
        None,
        description="Tool execution policy constraints",
    )
    inputs: Dict[str, Any] = Field(
        ..., description="Tool input parameters (supports template variables)"
    )
    outputs: Dict[str, str] = Field(
        ..., description="Output mapping (tool return field -> step output name)"
    )
    depends_on: List[str] = Field(
        default_factory=list,
        description="Dependencies: list of step IDs that must complete first",
    )
    condition: Optional[str] = Field(
        None,
        description="Optional execution condition (e.g., {{input.xxx or input.yyy}})",
    )
    for_each: Optional[str] = Field(
        None,
        description="Path to array to iterate over (e.g., step.search_photos.photos). "
        "Current item is available as {{item}} and index as {{index}}.",
    )
    gate: Optional[GateSpec] = Field(
        default=None,
        description="Optional gate configuration for human approval (pause/resume)",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_tool_or_slot(cls, values: Any) -> Any:
        """Ensure either tool (legacy) or tool_slot is provided, but not both."""
        if isinstance(values, dict):
            tool = values.get("tool")
            tool_slot = values.get("tool_slot")
            if not tool and not tool_slot:
                raise ValueError(
                    "Either 'tool' (legacy) or 'tool_slot' must be provided"
                )
            if tool and tool_slot:
                raise ValueError(
                    "Cannot specify both 'tool' and 'tool_slot'. Use 'tool_slot'."
                )
        return values


class ConcurrencyPolicy(BaseModel):
    """Runner-level concurrency control for playbook execution."""

    lock_key_input: str = Field(
        ...,
        description="Input parameter name whose value is used as lock key.",
    )
    max_parallel: int = Field(
        default=1,
        description="Maximum concurrent executions sharing the same lock key.",
    )
    lock_scope: str = Field(
        default="input",
        description="Lock scope: input, playbook, workspace.",
    )


class PlaybookJson(BaseModel):
    """Execution blueprint for runtime/ORS."""

    version: str = Field(default="1.0", description="Schema version")
    playbook_code: str = Field(..., description="Corresponding playbook code")
    kind: PlaybookKind = Field(
        ..., description="Playbook type: user_workflow or system_tool"
    )
    steps: List[PlaybookStep] = Field(..., description="Execution steps")
    inputs: Dict[str, PlaybookInput] = Field(
        ..., description="Playbook input definitions"
    )
    outputs: Dict[str, PlaybookOutput] = Field(
        ..., description="Playbook output definitions"
    )
    execution_profile: Optional[Dict[str, Any]] = Field(
        None,
        description="Execution profile for runtime selection.",
    )
    concurrency: Optional[ConcurrencyPolicy] = Field(
        None,
        description="Runner-level concurrency control lock constraints.",
    )
    lifecycle_hooks: Optional[Dict[str, Any]] = Field(
        None,
        description="Declarative lifecycle hooks (on_queue/on_start/on_complete/on_fail).",
    )

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

