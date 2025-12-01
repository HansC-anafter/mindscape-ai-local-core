"""
Personalized Playbook models
User-created variants of system Playbooks
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class PersonalizedPlaybook(BaseModel):
    """Personalized Playbook variant model"""

    id: str = Field(..., description="Unique variant identifier")
    profile_id: str = Field(..., description="Owner profile ID")
    base_playbook_code: str = Field(..., description="Base system Playbook code")
    base_version: str = Field(..., description="Base system Playbook version")

    variant_name: str = Field(..., description="Variant name (e.g., 'Simplified Version')")
    variant_description: Optional[str] = Field(None, description="Variant description")

    personalized_sop_content: Optional[str] = Field(
        None,
        description="Modified SOP content. If None, uses base Playbook SOP"
    )
    skip_steps: List[int] = Field(
        default_factory=list,
        description="List of step numbers to skip"
    )
    custom_checklist: List[str] = Field(
        default_factory=list,
        description="Personal checklist items"
    )
    execution_params: Dict[str, Any] = Field(
        default_factory=dict,
        description="Execution parameter overrides"
    )

    is_active: bool = Field(default=True, description="Whether variant is active")
    is_default: bool = Field(default=False, description="Whether this is the default variant")

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


class OptimizationSuggestion(BaseModel):
    """LLM-generated optimization suggestion"""

    suggestion_type: str = Field(
        ...,
        description="Type: skip_step, add_checklist, modify_sop, adjust_params"
    )
    title: str = Field(..., description="Suggestion title")
    description: str = Field(..., description="Detailed description")
    rationale: str = Field(..., description="Why this suggestion is made")

    # Suggestion-specific data
    step_number: Optional[int] = Field(None, description="Step number (for skip_step)")
    checklist_item: Optional[str] = Field(None, description="Checklist item (for add_checklist)")
    sop_modification: Optional[str] = Field(None, description="SOP modification (for modify_sop)")
    param_overrides: Optional[Dict[str, Any]] = Field(None, description="Parameter overrides")


class UsageAnalysis(BaseModel):
    """Playbook usage analysis results"""

    playbook_code: str
    profile_id: str

    # Usage statistics
    total_executions: int = 0
    successful_executions: int = 0
    failed_executions: int = 0
    average_duration_seconds: Optional[float] = None

    # Pattern analysis
    most_skipped_steps: List[int] = Field(default_factory=list)
    common_failure_reasons: List[str] = Field(default_factory=list)
    execution_times: List[str] = Field(default_factory=list)  # Time of day

    # Recommendations
    suggestions: List[OptimizationSuggestion] = Field(default_factory=list)


class CreateVariantRequest(BaseModel):
    """Request to create a personalized variant"""

    variant_name: str
    variant_description: Optional[str] = None
    personalized_sop_content: Optional[str] = None
    skip_steps: List[int] = Field(default_factory=list)
    custom_checklist: List[str] = Field(default_factory=list)
    execution_params: Dict[str, Any] = Field(default_factory=dict)
    is_default: bool = Field(default=False, description="Set as default variant")


class UpdateVariantRequest(BaseModel):
    """Request to update a personalized variant"""

    variant_name: Optional[str] = None
    variant_description: Optional[str] = None
    personalized_sop_content: Optional[str] = None
    skip_steps: Optional[List[int]] = None
    custom_checklist: Optional[List[str]] = None
    execution_params: Optional[Dict[str, Any]] = None
    is_active: Optional[bool] = None
    is_default: Optional[bool] = None
