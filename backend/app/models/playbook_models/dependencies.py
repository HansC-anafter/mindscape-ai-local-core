"""Dependency and agent definition models for playbooks."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field, ValidationInfo, field_validator


class ToolDependency(BaseModel):
    """
    Tool dependency declaration.

    Supports three tool types:
    1. builtin
    2. langchain
    3. mcp
    """

    type: Literal["builtin", "langchain", "mcp"] = Field(
        ..., description="Tool type: builtin, langchain, or mcp"
    )
    name: str = Field(..., description="Tool name or identifier")
    source: Optional[str] = Field(
        None,
        description="Tool source: full class path for LangChain, server ID for MCP",
    )
    config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool configuration (API keys, environment variables, etc.), "
        "supports ${VAR} syntax",
    )
    required: bool = Field(
        default=True,
        description="Whether the tool is required (execution blocked if missing)",
    )
    fallback: Optional[str] = Field(
        None, description="Fallback tool name (when main tool is unavailable)"
    )
    description: Optional[str] = Field(None, description="Tool purpose description")

    @field_validator("source")
    @classmethod
    def validate_source(cls, v: str | None, info: ValidationInfo) -> str | None:
        """Validate source field."""
        tool_type = info.data.get("type")
        if tool_type == "langchain" and not v:
            raise ValueError("LangChain tools must provide source (full class path)")
        return v


class AgentDefinition(BaseModel):
    """Agent role spec within a playbook roster."""

    agent_id: str = Field(
        ..., description="Unique agent ID (e.g., researcher, writer, reviewer)"
    )
    agent_name: str = Field(..., description="Display name")
    system_prompt: Optional[str] = Field(
        None, description="Agent-specific system prompt"
    )
    role: Optional[str] = Field(
        None, description="Agent role (e.g., researcher, engineer, reviewer)"
    )
    tools: List[str] = Field(
        default_factory=list, description="Tool IDs this agent can use"
    )
    memory_scope: Optional[str] = Field(
        None, description="Memory scope: workspace/session/task"
    )
    responsibility_boundary: Optional[str] = Field(
        None, description="Responsibility boundary description"
    )
    capability_profile: Optional[str] = Field(
        None, description="Capability profile for this agent"
    )
    critical_rules: Optional[List[str]] = Field(
        default=None,
        description="Hard constraints this role must never violate",
    )
    communication_style: Optional[str] = Field(
        default=None,
        description="Tone, language, and formatting preferences",
    )
    success_metrics: Optional[List[str]] = Field(
        default=None,
        description="Measurable quality criteria for role output",
    )
