"""
Core Export Models (Opensource)
Defines export formats for local backup and portability
"""

from datetime import datetime
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class BackupConfiguration(BaseModel):
    """
    Complete backup of user configuration (Opensource)

    Includes all data including encrypted credentials.
    Used for backup/restore on the same or different local instance.
    This format is designed for local use and data preservation.
    """

    # Version info
    backup_version: str = Field(default="1.0.0", description="Backup format version")
    backup_timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field(default="my-agent-mindscape", description="Source system")

    # Complete user data (including credentials - encrypted)
    mindscape_profile: Dict[str, Any] = Field(..., description="Complete mindscape profile")
    intent_cards: List[Dict[str, Any]] = Field(default_factory=list, description="All intent cards")
    ai_roles: List[Dict[str, Any]] = Field(default_factory=list, description="AI role configurations")
    playbooks: List[Dict[str, Any]] = Field(default_factory=list, description="Playbook definitions")
    tool_connections: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Tool connections (with encrypted credentials)"
    )

    # System configuration
    agent_backend_config: Dict[str, Any] = Field(
        default_factory=dict,
        description="Agent backend configuration"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Backup metadata (creation date, version, etc.)"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class PortableConfiguration(BaseModel):
    """
    Portable configuration (Opensource)

    No sensitive data, can be shared with other local users or platforms.
    Recipients will need to fill in their own credentials.
    This format is designed for configuration sharing and migration.
    """

    # Version info
    portable_version: str = Field(default="1.0.0", description="Portable format version")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    source: str = Field(default="my-agent-mindscape", description="Source system")

    # Template identification
    config_name: str = Field(..., description="Configuration name")
    config_description: str = Field(default="", description="Configuration description")
    config_tags: List[str] = Field(default_factory=list, description="Configuration tags")

    # Sanitized configuration (no personal data)
    mindscape_template: Dict[str, Any] = Field(
        ...,
        description="Mindscape profile template (without email and personal data)"
    )

    # AI roles and configurations
    ai_roles: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="AI role configurations"
    )

    # Playbooks
    playbooks: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Playbook definitions"
    )

    # Tool connection templates (structure only, no credentials)
    tool_connection_templates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Tool connection templates (structure only, no credentials)"
    )

    # Role-Tool associations
    role_tool_mappings: Dict[str, List[str]] = Field(
        default_factory=dict,
        description="Mapping of role_id to tool_ids"
    )

    # Intent cards (optional, can be used as capability templates)
    intent_templates: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Intent card templates (optional)"
    )

    # Confirmed habits (optional, can be excluded for privacy)
    confirmed_habits: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Confirmed habit preferences (optional, can be excluded)"
    )

    # Metadata
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata about this configuration"
    )

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ExportPreview(BaseModel):
    """
    Preview of what will be exported

    Used in UI to show user what data will be included in the export.
    """

    # Summary counts
    mindscape_profile_included: bool
    intent_cards_count: int
    ai_roles_count: int
    playbooks_count: int
    tool_connections_count: int

    # Details
    ai_roles: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of role names and descriptions"
    )
    playbooks: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of playbook names and descriptions"
    )
    tools: List[Dict[str, str]] = Field(
        default_factory=list,
        description="List of tool types and names"
    )

    # What will be filtered (for portable/template exports)
    filtered_fields: List[str] = Field(
        default_factory=list,
        description="List of field names that will be filtered out (e.g., 'email', 'api_keys')"
    )

    # Estimated export size
    estimated_size_kb: float = Field(0.0, description="Estimated export size in KB")

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class BackupRequest(BaseModel):
    """Request to create a backup"""
    profile_id: str
    include_credentials: bool = Field(default=True, description="Include encrypted credentials")


class PortableExportRequest(BaseModel):
    """Request to export portable configuration"""
    profile_id: str
    config_name: str
    config_description: str = ""
    config_tags: List[str] = Field(default_factory=list)
    include_intent_cards: bool = Field(default=True, description="Include intent cards as templates")
    include_confirmed_habits: bool = Field(default=True, description="Include confirmed habits (can be excluded for privacy)")


class ExportResponse(BaseModel):
    """Response from export operation"""
    success: bool
    export_id: str
    export_type: str  # "backup" or "portable"
    download_url: Optional[str] = None
    exported_at: datetime = Field(default_factory=datetime.utcnow)
    file_size_bytes: int = 0

    class Config:
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }
