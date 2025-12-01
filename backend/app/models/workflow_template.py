"""
Workflow Template Models

Defines data models for workflow templates, user-defined workflows, and version management.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any, Literal
from pydantic import BaseModel, Field

from .playbook import WorkflowStep, PlaybookKind, InteractionMode


class WorkflowTemplateVariable(BaseModel):
    """Template variable definition"""
    name: str = Field(..., description="Variable name")
    type: str = Field(..., description="Variable type (string, integer, list, etc.)")
    description: Optional[str] = Field(None, description="Variable description")
    default: Optional[Any] = Field(None, description="Default value")
    required: bool = Field(default=True, description="Whether this variable is required")


class WorkflowTemplate(BaseModel):
    """Workflow template definition"""
    template_id: str = Field(..., description="Unique template identifier")
    name: str = Field(..., description="Template name")
    description: str = Field(default="", description="Template description")
    version: str = Field(default="1.0.0", description="Template version")
    category: Optional[str] = Field(None, description="Template category")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    steps: List[WorkflowStep] = Field(..., description="Template workflow steps")
    variables: Dict[str, WorkflowTemplateVariable] = Field(
        default_factory=dict,
        description="Template variables that can be parameterized"
    )
    context_template: Dict[str, Any] = Field(
        default_factory=dict,
        description="Template for initial context"
    )
    owner: Optional[Dict[str, Any]] = Field(
        default_factory=lambda: {"type": "system"},
        description="Template owner information"
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class UserWorkflow(BaseModel):
    """User-defined workflow"""
    workflow_id: str = Field(..., description="Unique workflow identifier")
    name: str = Field(..., description="Workflow name")
    description: str = Field(default="", description="Workflow description")
    template_id: Optional[str] = Field(None, description="Source template ID if created from template")
    version: str = Field(default="1.0.0", description="Workflow version")
    steps: List[WorkflowStep] = Field(..., description="Workflow steps")
    context: Dict[str, Any] = Field(default_factory=dict, description="Initial context")
    workspace_id: str = Field(..., description="Workspace ID this workflow belongs to")
    profile_id: str = Field(..., description="User profile ID who created this workflow")
    is_public: bool = Field(default=False, description="Whether this workflow is publicly shareable")
    tags: List[str] = Field(default_factory=list, description="Tags for categorization")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class WorkflowVersion(BaseModel):
    """Workflow version record"""
    version_id: str = Field(..., description="Unique version identifier")
    workflow_id: str = Field(..., description="Workflow ID this version belongs to")
    version: str = Field(..., description="Version string (e.g., '1.0.0', '2.1.3')")
    steps: List[WorkflowStep] = Field(..., description="Workflow steps at this version")
    context: Dict[str, Any] = Field(default_factory=dict, description="Initial context at this version")
    changelog: Optional[str] = Field(None, description="Changelog for this version")
    created_by: str = Field(..., description="User profile ID who created this version")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    is_current: bool = Field(default=False, description="Whether this is the current active version")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class CreateWorkflowTemplateRequest(BaseModel):
    """Request model for creating a workflow template"""
    template_id: str
    name: str
    description: str = ""
    category: Optional[str] = None
    tags: List[str] = Field(default_factory=list)
    steps: List[Dict[str, Any]]
    variables: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    context_template: Dict[str, Any] = Field(default_factory=dict)


class CreateUserWorkflowRequest(BaseModel):
    """Request model for creating a user-defined workflow"""
    workflow_id: str
    name: str
    description: str = ""
    template_id: Optional[str] = None
    steps: List[Dict[str, Any]]
    context: Dict[str, Any] = Field(default_factory=dict)
    is_public: bool = False
    tags: List[str] = Field(default_factory=list)


class InstantiateTemplateRequest(BaseModel):
    """Request model for instantiating a template"""
    template_id: str
    variable_values: Dict[str, Any] = Field(default_factory=dict)
    context_overrides: Dict[str, Any] = Field(default_factory=dict)

