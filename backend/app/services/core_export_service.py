"""
Core Export Service (Opensource)
Handles backup and portable configuration export for local use
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from backend.app.models.core_export import (
    BackupConfiguration,
    PortableConfiguration,
    ExportPreview,
    BackupRequest,
    PortableExportRequest,
)
from backend.app.models.mindscape import MindscapeProfile, IntentCard
from backend.app.models.playbook import Playbook
from backend.app.models.ai_role import AIRoleConfig
from backend.app.models.tool_connection import ToolConnectionTemplate
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_store import PlaybookStore
from backend.app.services.ai_role_store import AIRoleStore
from backend.app.services.tool_registry import ToolRegistryService


class CoreExportService:
    """
    Core export service for opensource version

    This service handles:
    1. Complete backup (with encrypted credentials)
    2. Portable configuration export (without credentials)
    3. Configuration sharing between local users
    """

    def __init__(
        self,
        mindscape_store: Optional[MindscapeStore] = None,
        playbook_store: Optional[PlaybookStore] = None,
        ai_role_store: Optional[AIRoleStore] = None,
        tool_registry: Optional[ToolRegistryService] = None,
    ):
        self.mindscape_store = mindscape_store or MindscapeStore()
        self.playbook_store = playbook_store or PlaybookStore()
        self.ai_role_store = ai_role_store or AIRoleStore()
        import os
        data_dir = os.getenv("DATA_DIR", "./data")
        self.tool_registry = tool_registry or ToolRegistryService(data_dir=data_dir)

    async def create_backup(self, request: BackupRequest) -> BackupConfiguration:
        """
        Create complete backup with all data (including encrypted credentials)

        Use case: User wants to backup their entire configuration for restore.
        """
        profile_id = request.profile_id

        # Get all data
        profile = await self.mindscape_store.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        intents = await self.mindscape_store.get_intents_by_profile(profile_id)
        ai_roles = self.ai_role_store.get_enabled_roles(profile_id)
        playbooks = self.playbook_store.list_playbooks()
        tool_connections = self.tool_registry.get_connections_by_profile(profile_id)

        # Create backup (including credentials if requested)
        backup = BackupConfiguration(
            backup_version="1.0.0",
            backup_timestamp=datetime.utcnow(),
            source="my-agent-mindscape",
            mindscape_profile=profile.dict(),
            intent_cards=[intent.dict() for intent in intents],
            ai_roles=[role.dict() for role in ai_roles],
            playbooks=[pb.dict() for pb in playbooks],
            tool_connections=[
                self._serialize_connection_for_backup(conn, request.include_credentials)
                for conn in tool_connections
            ],
            agent_backend_config=self._get_backend_config(),
            metadata={
                "created_at": datetime.utcnow().isoformat(),
                "profile_id": profile_id,
                "include_credentials": request.include_credentials,
            }
        )

        return backup

    async def create_portable_config(
        self,
        request: PortableExportRequest
    ) -> PortableConfiguration:
        """
        Create portable configuration (without sensitive data)

        Use case: User wants to share their configuration with others.
        """
        profile_id = request.profile_id

        # Get all data
        profile = await self.mindscape_store.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        intents = await self.mindscape_store.get_intents_by_profile(profile_id)
        ai_roles = self.ai_role_store.get_enabled_roles(profile_id)
        playbooks = self.playbook_store.list_playbooks()
        tool_templates_data = self.tool_registry.export_as_templates(profile_id)

        # Get confirmed habits (optional, can be excluded for privacy)
        confirmed_habits = []
        if getattr(request, 'include_confirmed_habits', True):
            try:
                from backend.app.services.habit_store import HabitStore
                habit_store = HabitStore()
                confirmed = habit_store.get_confirmed_habits(profile_id)
                confirmed_habits = [
                    {
                        "habit_key": habit.habit_key,
                        "habit_value": habit.habit_value,
                        "habit_category": habit.habit_category.value,
                        "confidence": habit.confidence,
                        "evidence_count": habit.evidence_count,
                        "first_seen_at": habit.first_seen_at.isoformat() if habit.first_seen_at else None,
                        "last_seen_at": habit.last_seen_at.isoformat() if habit.last_seen_at else None,
                    }
                    for habit in confirmed
                ]
            except Exception as e:
                # If habit store is not available, continue without habits
                import logging
                logger = logging.getLogger(__name__)
                logger.warning(f"Failed to include confirmed habits in export: {e}")

        # Create portable configuration
        portable = PortableConfiguration(
            portable_version="1.0.0",
            created_at=datetime.utcnow(),
            source="my-agent-mindscape",
            config_name=request.config_name,
            config_description=request.config_description,
            config_tags=request.config_tags,
            mindscape_template=self._sanitize_profile(profile),
            ai_roles=[self._serialize_ai_role(role) for role in ai_roles],
            playbooks=[self._serialize_playbook(pb) for pb in playbooks],
            tool_connection_templates=[template.dict() for template in tool_templates],
            role_tool_mappings=self._build_role_tool_mappings(ai_roles),
            intent_templates=[
                self._serialize_intent_template(intent)
                for intent in intents
            ] if request.include_intent_cards else [],
            confirmed_habits=confirmed_habits,
            metadata={
                "created_at": datetime.utcnow().isoformat(),
                "source_profile_id": profile_id,
            }
        )

        return portable

    async def preview_export(self, profile_id: str) -> ExportPreview:
        """
        Generate a preview of what will be exported
        """
        profile = await self.mindscape_store.get_profile(profile_id)
        intents = await self.mindscape_store.get_intents_by_profile(profile_id)
        ai_roles = self.ai_role_store.get_enabled_roles(profile_id)
        playbooks = self.playbook_store.list_playbooks()
        tool_connections = self.tool_registry.get_connections_by_profile(profile_id)

        return ExportPreview(
            mindscape_profile_included=profile is not None,
            intent_cards_count=len(intents),
            ai_roles_count=len(ai_roles),
            playbooks_count=len(playbooks),
            tool_connections_count=len(tool_connections),
            ai_roles=[
                {"id": role.id, "name": role.name, "description": role.description}
                for role in ai_roles
            ],
            playbooks=[
                {"code": pb.metadata.playbook_code, "name": pb.metadata.name, "description": pb.metadata.description}
                for pb in playbooks
            ],
            tools=[
                {"type": conn.tool_type, "name": conn.name}
                for conn in tool_connections
            ],
            filtered_fields=[
                "email",
                "api_key",
                "api_secret",
                "oauth_token",
                "oauth_refresh_token",
            ],
            estimated_size_kb=self._estimate_export_size(profile, intents, ai_roles, playbooks),
        )

    def save_to_file(
        self,
        config: BackupConfiguration | PortableConfiguration,
        output_dir: str = "exports"
    ) -> str:
        """Save configuration to JSON file"""
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")

        if isinstance(config, BackupConfiguration):
            filename = f"backup_{timestamp}.json"
        else:
            name = config.config_name.replace(' ', '_')
            filename = f"portable_{name}_{timestamp}.json"

        filepath = Path(output_dir) / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(config.dict(), f, indent=2, ensure_ascii=False)

        return str(filepath)

    # Private helper methods

    def _sanitize_profile(self, profile: MindscapeProfile) -> Dict[str, Any]:
        """Remove personal data from profile"""
        return {
            "default_roles": profile.roles,
            "default_domains": profile.domains,
            "default_preferences": profile.preferences.dict(),
            "self_description_template": profile.self_description,
            "tags": profile.tags,
            # Filtered: email, external_ref
        }

    def _serialize_ai_role(self, role: AIRoleConfig) -> Dict[str, Any]:
        """Serialize AI role for portable export"""
        return {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "agent_type": role.agent_type,
            "icon": role.icon,
            "playbooks": role.playbooks,
            "suggested_tasks": role.suggested_tasks,
            "tools": role.tools,
            "mindscape_profile_override": role.mindscape_profile_override,
            "is_custom": role.is_custom,
        }

    def _serialize_playbook(self, playbook: Playbook) -> Dict[str, Any]:
        """Serialize playbook for export"""
        return {
            "playbook_code": playbook.metadata.playbook_code,
            "version": playbook.metadata.version,
            "name": playbook.metadata.name,
            "description": playbook.metadata.description,
            "tags": playbook.metadata.tags,
            "entry_agent_type": playbook.metadata.entry_agent_type,
            "required_tools": playbook.metadata.required_tools,
            "runtime_handler": playbook.metadata.runtime_handler,
            "sop_content": playbook.sop_content,
        }

    def _serialize_intent_template(self, intent: IntentCard) -> Dict[str, Any]:
        """Serialize intent as template"""
        return {
            "title": intent.title,
            "description": intent.description,
            "tags": intent.tags,
            "category": intent.category,
            "priority": intent.priority.value if intent.priority else "medium",
        }

    def _serialize_connection_for_backup(
        self,
        conn,
        include_credentials: bool
    ) -> Dict[str, Any]:
        """Serialize connection for backup (optionally with credentials)"""
        data = conn.dict()

        if not include_credentials:
            # Remove sensitive fields
            data.pop("api_key", None)
            data.pop("api_secret", None)
            data.pop("oauth_token", None)
            data.pop("oauth_refresh_token", None)

        return data

    def _build_role_tool_mappings(self, ai_roles: List[AIRoleConfig]) -> Dict[str, List[str]]:
        """Build role-to-tool mappings"""
        return {
            role.id: role.tools
            for role in ai_roles
            if role.tools
        }

    def _get_backend_config(self) -> Dict[str, Any]:
        """Get agent backend configuration"""
        return {
            "default_backend_type": "local_llm",
            "supported_backends": ["local_llm", "remote_crs"],
        }

    def _estimate_export_size(
        self,
        profile: Optional[MindscapeProfile],
        intents: List[IntentCard],
        ai_roles: List[AIRoleConfig],
        playbooks: List[Playbook],
    ) -> float:
        """Estimate export size in KB"""
        size = 0.0
        if profile:
            size += 1.0
        size += len(intents) * 0.5
        size += len(ai_roles) * 0.3
        size += len(playbooks) * 2.0
        return round(size, 2)
