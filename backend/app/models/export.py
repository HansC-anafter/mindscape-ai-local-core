"""
External Extension Export Models
Defines export formats for external platform integration
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class ConsoleKitTemplate(BaseModel):
    """
    External extension chainagent template format (Platform Extension)

    This format is for external platform integration, creating chainagent blueprints.
    Designed for productization and multi-tenant scenarios.
    """

    # Version info
    export_version: str = Field(default="1.0.0", description="Export format version")
    export_timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field(default="my-agent-mindscape", description="Source system")

    # Template identification
    template_name: str = Field(..., description="Template name")
    template_description: str = Field(default="", description="Template description")
    template_tags: List[str] = Field(default_factory=list, description="Template tags")

    # Mindscape profile template (sanitized)
    mindscape_template: Dict[str, Any] = Field(
        ..., description="Mindscape profile template (without personal data)"
    )

    # Intent cards (converted to capability packs)
    capability_packs: List[Dict[str, Any]] = Field(
        default_factory=list, description="Capability packs derived from intent cards"
    )

    # AI Roles & Configurations
    ai_roles: List[Dict[str, Any]] = Field(
        default_factory=list, description="AI role configurations"
    )

    # Playbooks
    playbooks: List[Dict[str, Any]] = Field(
        default_factory=list, description="Playbook definitions"
    )

    # Tool connection templates (without credentials)
    tool_templates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Tool connection templates (structure only, no credentials)",
    )

    # Workspace artifacts (brand content, documents, etc.)
    artifacts: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Workspace artifacts including brand content, documents, and other structured data",
    )

    # Role-Tool associations
    role_tool_mappings: Dict[str, List[str]] = Field(
        default_factory=dict, description="Mapping of role_id to tool_ids"
    )

    # Agent backend configuration (sanitized)
    agent_backend_config: Dict[str, Any] = Field(
        default_factory=dict, description="Agent backend configuration template"
    )

    # Statistics and metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata about this template"
    )

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ExportPreview(BaseModel):
    """
    Preview of what will be exported

    Used in UI to show user what data will be included in the template.
    """

    # Summary counts
    mindscape_profile_included: bool
    intent_cards_count: int
    ai_roles_count: int
    playbooks_count: int
    tool_connections_count: int

    # Details
    ai_roles: List[Dict[str, str]] = Field(
        default_factory=list, description="List of role names and descriptions"
    )
    playbooks: List[Dict[str, str]] = Field(
        default_factory=list, description="List of playbook names and descriptions"
    )
    tools: List[Dict[str, str]] = Field(
        default_factory=list, description="List of tool types and names"
    )

    # What will be filtered
    filtered_fields: List[str] = Field(
        default_factory=list,
        description="List of field names that will be filtered out (e.g., 'email', 'api_keys')",
    )

    # Estimated template size
    estimated_size_kb: float = Field(0.0, description="Estimated template size in KB")

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ConsoleKitExportRequest(BaseModel):
    """Request to export as external extension template"""

    profile_id: str
    template_name: str
    template_description: str = ""
    template_tags: List[str] = Field(default_factory=list)

    # Options
    include_intent_cards: bool = Field(
        default=True, description="Include intent cards as capability packs"
    )
    include_usage_statistics: bool = Field(
        default=False, description="Include usage statistics in metadata"
    )


class ConsoleKitExportResponse(BaseModel):
    """Response from external extension template export"""

    success: bool
    template_id: str
    download_url: Optional[str] = None
    exported_at: datetime = Field(default_factory=datetime.utcnow)
    file_size_bytes: int = 0

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ConsoleKitImportValidationResult(BaseModel):
    """
    Result of external extension template validation

    This is used by external extension platforms to validate imported templates.
    """

    is_valid: bool
    export_version: str
    template_name: str

    # Validation details
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

    # Contents summary
    contains_mindscape: bool = False
    contains_ai_roles: bool = False
    contains_playbooks: bool = False
    contains_tools: bool = False

    ai_roles_count: int = 0
    playbooks_count: int = 0
    tools_count: int = 0

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}
