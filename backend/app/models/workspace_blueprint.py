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
        default_factory=list,
        description="Primary goals (1-3 items)"
    )
    out_of_scope: List[str] = Field(
        default_factory=list,
        description="Explicit out-of-scope items"
    )
    success_criteria: List[str] = Field(
        default_factory=list,
        description="Success criteria"
    )


class ToolConnectionTemplate(BaseModel):
    """Tool connection template"""
    tool_type: str = Field(
        ...,
        description="Tool type (e.g., 'wordpress', 'notion')"
    )
    danger_level: str = Field(
        ...,
        description="Danger level: 'low' / 'medium' / 'high'"
    )
    default_readonly: bool = Field(
        default=False,
        description="Default read-only mode"
    )
    allowed_roles: List[str] = Field(
        default_factory=list,
        description="Allowed AI role IDs"
    )


class WorkspaceBlueprint(BaseModel):
    """Workspace blueprint configuration"""

    # Brief (from Seed digest or wizard generation)
    brief: Optional[str] = Field(
        None,
        description="Workspace brief (1-2 paragraphs): what to do / what not to do / success criteria"
    )

    # 1. Goals and boundaries
    goals: Optional[WorkspaceGoals] = None

    # 2. Initial intent set
    initial_intents: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Initial intent cards (3-7 items)"
    )

    # 3. AI Team roster
    ai_team: List[str] = Field(
        default_factory=list,
        description="AI role IDs for this workspace"
    )

    # 4. Playbook Pack
    playbooks: List[str] = Field(
        default_factory=list,
        description="Playbook codes to preload"
    )

    # 5. Tool Connections
    # Important: Use List instead of Dict for sortability and multiple entries,
    # and to align with starter-kit YAML format
    tool_connections: List[ToolConnectionTemplate] = Field(
        default_factory=list,
        description="Tool connection templates and risk gates"
    )

    # First playbook to run
    first_playbook: Optional[str] = Field(
        None,
        description="First playbook to run after workspace creation"
    )

    # Seed digest sub-field (optional, to avoid blueprint bloat)
    seed_digest: Optional[Dict[str, Any]] = Field(
        None,
        description="Seed digest metadata: facts, unknowns, next_actions (optional)"
    )

