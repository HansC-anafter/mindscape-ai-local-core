"""
Workspace Blueprint models for workspace launch enhancement

Defines the structure for workspace configuration blueprints,
including goals, initial intents, AI team, playbooks, and tool connections.
"""

from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional


class WorkspaceGoals(BaseModel):
    """Workspace goals and boundaries"""

    primary_goals: List[str] = Field(
        default_factory=list, description="Primary goals (1-3 items)"
    )
    out_of_scope: List[str] = Field(
        default_factory=list, description="Explicit out-of-scope items"
    )
    success_criteria: List[str] = Field(
        default_factory=list, description="Success criteria"
    )


class ToolConnectionTemplate(BaseModel):
    """Tool connection template"""

    tool_type: str = Field(..., description="Tool type (e.g., 'wordpress', 'notion')")
    danger_level: str = Field(
        ..., description="Danger level: 'low' / 'medium' / 'high'"
    )
    default_readonly: bool = Field(default=False, description="Default read-only mode")
    allowed_roles: List[str] = Field(
        default_factory=list, description="Allowed AI role IDs"
    )


class WorkspaceInstruction(BaseModel):
    """Skill-inspired workspace-level system instruction.

    Injected into all LLM calls as workspace base context.
    Field lengths constrained to prevent prompt injection bloat (OWASP LLM01).
    """

    persona: Optional[str] = Field(
        None,
        max_length=500,
        description="Who is this AI in this workspace, e.g. 'You are a brand strategist for a yoga studio.'",
    )
    goals: List[str] = Field(
        default_factory=list,
        description="What this workspace aims to achieve (1-10 items)",
    )
    anti_goals: List[str] = Field(
        default_factory=list,
        description="What this workspace must NOT do (1-10 items)",
    )
    style_rules: List[str] = Field(
        default_factory=list,
        description="Tone, language, formatting preferences (1-10 items)",
    )
    domain_context: Optional[str] = Field(
        None,
        max_length=2000,
        description="Free-form domain knowledge the AI should know about",
    )
    version: int = Field(
        default=1, description="Instruction version for tracking iterations"
    )


class WorkspaceBlueprint(BaseModel):
    """Workspace blueprint configuration"""

    # Workspace Instruction (skill-inspired, LLM-injectable)
    instruction: Optional[WorkspaceInstruction] = Field(
        None,
        description="Structured workspace-level system instruction, injected into all LLM calls",
    )

    # Brief (legacy: from Seed digest or wizard generation)
    brief: Optional[str] = Field(
        None,
        description="Workspace brief (1-2 paragraphs): what to do / what not to do / success criteria",
    )

    # Goals and boundaries
    goals: Optional[WorkspaceGoals] = None

    # Initial intent set
    initial_intents: List[Dict[str, Any]] = Field(
        default_factory=list, description="Initial intent cards (3-7 items)"
    )

    # AI Team roster
    ai_team: List[str] = Field(
        default_factory=list, description="AI role IDs for this workspace"
    )

    # Playbook Pack
    playbooks: List[str] = Field(
        default_factory=list, description="Playbook codes to preload"
    )

    # Tool Connections
    # Important: Use List instead of Dict for sortability and multiple entries,
    # and to align with starter-kit YAML format
    tool_connections: List[ToolConnectionTemplate] = Field(
        default_factory=list, description="Tool connection templates and risk gates"
    )

    # First playbook to run
    first_playbook: Optional[str] = Field(
        None, description="First playbook to run after workspace creation"
    )

    # Seed digest sub-field (optional, to avoid blueprint bloat)
    seed_digest: Optional[Dict[str, Any]] = Field(
        None,
        description="Seed digest metadata: facts, unknowns, next_actions (optional)",
    )
