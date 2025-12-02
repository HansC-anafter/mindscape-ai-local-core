"""
Export Service
Handles exporting user configuration as templates for console-kit
"""

import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from pathlib import Path

from backend.app.models.export import ExportedConfiguration, ExportPreview, ExportRequest
from backend.app.models.mindscape import MindscapeProfile, IntentCard
from backend.app.models.playbook import Playbook
from backend.app.models.ai_role import AIRoleConfig
from backend.app.models.tool_connection import ToolConnectionTemplate
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_store import PlaybookStore
from backend.app.services.ai_role_store import AIRoleStore
from backend.app.services.tool_connection_store import ToolConnectionStore


class ExportService:
    """
    Service for exporting user configuration as templates

    This service handles:
    1. Collecting all configuration data
    2. Filtering out personal/sensitive information
    3. Converting to template format
    4. Generating export files
    """

    def __init__(
        self,
        mindscape_store: Optional[MindscapeStore] = None,
        playbook_store: Optional[PlaybookStore] = None,
        ai_role_store: Optional[AIRoleStore] = None,
        tool_connection_store: Optional[ToolConnectionStore] = None,
    ):
        self.mindscape_store = mindscape_store or MindscapeStore()
        self.playbook_store = playbook_store or PlaybookStore()
        self.ai_role_store = ai_role_store or AIRoleStore()
        self.tool_connection_store = tool_connection_store or ToolConnectionStore()

    async def export_as_template(self, request: ExportRequest) -> ExportedConfiguration:
        """
        Export complete configuration as a template

        Personal data (email, API keys) will be filtered out.
        """
        profile_id = request.profile_id

        # 1. Get mindscape profile
        profile = await self.mindscape_store.get_profile(profile_id)
        if not profile:
            raise ValueError(f"Profile not found: {profile_id}")

        # 2. Convert profile to template (sanitized)
        mindscape_template = self._sanitize_profile(profile)

        # 3. Get and convert intent cards to capability packs
        capability_packs = []
        if request.include_intent_cards:
            intents = await self.mindscape_store.get_intents_by_profile(profile_id)
            capability_packs = self._convert_intents_to_capability_packs(intents)

        # 4. Get AI role configurations
        ai_roles = self.ai_role_store.get_enabled_roles(profile_id)
        ai_roles_data = [self._serialize_ai_role(role) for role in ai_roles]

        # 5. Get playbooks
        playbooks = self.playbook_store.list_playbooks()
        playbooks_data = [self._serialize_playbook(pb) for pb in playbooks]

        # 6. Get tool connection templates (without credentials)
        tool_templates = self.tool_connection_store.export_as_templates(profile_id)
        tool_templates_data = [template.dict() for template in tool_templates]

        # 7. Build role-tool mappings
        role_tool_mappings = self._build_role_tool_mappings(ai_roles)

        # 8. Get agent backend config (sanitized)
        agent_backend_config = self._get_agent_backend_config_template()

        # 9. Build metadata
        metadata = self._build_metadata(
            profile,
            ai_roles,
            playbooks,
            request.include_usage_statistics
        )

        # 10. Create exported configuration
        exported = ExportedConfiguration(
            export_version="1.0.0",
            export_timestamp=datetime.utcnow(),
            source="my-agent-mindscape",
            template_name=request.template_name,
            template_description=request.template_description,
            template_tags=request.template_tags,
            mindscape_template=mindscape_template,
            capability_packs=capability_packs,
            ai_roles=ai_roles_data,
            playbooks=playbooks_data,
            tool_templates=tool_templates_data,
            role_tool_mappings=role_tool_mappings,
            agent_backend_config=agent_backend_config,
            metadata=metadata,
        )

        return exported

    async def preview_export(self, profile_id: str) -> ExportPreview:
        """
        Generate a preview of what will be exported

        Used in UI to show user what data will be included.
        """
        # Get all data
        profile = await self.mindscape_store.get_profile(profile_id)
        intents = await self.mindscape_store.get_intents_by_profile(profile_id)
        ai_roles = self.ai_role_store.get_enabled_roles(profile_id)
        playbooks = self.playbook_store.list_playbooks()
        tool_connections = self.tool_connection_store.get_connections_by_profile(profile_id)

        # Build preview
        preview = ExportPreview(
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

        return preview

    def _sanitize_profile(self, profile: MindscapeProfile) -> Dict[str, Any]:
        """
        Convert profile to template format, removing personal data
        """
        return {
            "default_roles": profile.roles,
            "default_domains": profile.domains,
            "default_preferences": profile.preferences.dict(),
            "self_description_template": profile.self_description,  # As example
            "tags": profile.tags,
            # Filtered: email, external_ref (those are personal)
        }

    def _convert_intents_to_capability_packs(self, intents: List[IntentCard]) -> List[Dict[str, Any]]:
        """
        Convert intent cards to capability packs

        Capability packs are reusable templates derived from user's intents.
        """
        capability_packs = []

        for intent in intents:
            pack = {
                "name": intent.title,
                "description": intent.description,
                "tags": intent.tags,
                "category": intent.category,
                "priority_level": intent.priority.value if intent.priority else "medium",
                # Metadata preserved but not personal data
            }
            capability_packs.append(pack)

        return capability_packs

    def _serialize_ai_role(self, role: AIRoleConfig) -> Dict[str, Any]:
        """Serialize AI role configuration"""
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
        """Serialize playbook with all P1 fields"""
        return {
            "playbook_code": playbook.metadata.playbook_code,
            "version": playbook.metadata.version,
            "locale": playbook.metadata.locale,
            "name": playbook.metadata.name,
            "description": playbook.metadata.description,
            "tags": playbook.metadata.tags,
            "entry_agent_type": playbook.metadata.entry_agent_type,
            "onboarding_task": playbook.metadata.onboarding_task,
            "icon": playbook.metadata.icon,
            "required_tools": playbook.metadata.required_tools,
            "scope": playbook.metadata.scope,
            "runtime_handler": playbook.metadata.runtime_handler,
            "sop_content": playbook.sop_content,
            # Filtered: owner (personal info), user_notes (personal)
        }

    def _build_role_tool_mappings(self, ai_roles: List[AIRoleConfig]) -> Dict[str, List[str]]:
        """Build mappings of role_id to tool_ids"""
        mappings = {}
        for role in ai_roles:
            if role.tools:
                mappings[role.id] = role.tools
        return mappings

    def _get_agent_backend_config_template(self) -> Dict[str, Any]:
        """Get agent backend configuration template (without API keys)"""
        # TODO: Implement based on actual config_store
        return {
            "default_backend_type": "local_llm",
            "supported_backends": ["local_llm", "remote_crs"],
            # API keys not included (security)
        }

    def _build_metadata(
        self,
        profile: MindscapeProfile,
        ai_roles: List[AIRoleConfig],
        playbooks: List[Playbook],
        include_usage_statistics: bool,
    ) -> Dict[str, Any]:
        """Build metadata about the template"""
        metadata = {
            "created_from_profile_version": profile.version,
            "export_date": datetime.utcnow().isoformat(),
            "ai_roles_count": len(ai_roles),
            "playbooks_count": len(playbooks),
        }

        if include_usage_statistics:
            total_usage = sum(role.usage_count for role in ai_roles)
            most_used_role = max(ai_roles, key=lambda r: r.usage_count) if ai_roles else None

            metadata["usage_statistics"] = {
                "total_ai_role_usage": total_usage,
                "most_used_role": most_used_role.name if most_used_role else None,
            }

        return metadata

    def _estimate_export_size(
        self,
        profile: Optional[MindscapeProfile],
        intents: List[IntentCard],
        ai_roles: List[AIRoleConfig],
        playbooks: List[Playbook],
    ) -> float:
        """Estimate export size in KB"""
        # Rough estimation
        size = 0.0

        if profile:
            size += 1.0  # Profile template ~1KB

        size += len(intents) * 0.5  # Each intent ~0.5KB
        size += len(ai_roles) * 0.3  # Each role ~0.3KB
        size += len(playbooks) * 2.0  # Each playbook ~2KB (includes SOP content)

        return round(size, 2)

    def save_export_to_file(self, exported: ExportedConfiguration, output_dir: str = "exports") -> str:
        """
        Save exported configuration to a JSON file

        Returns the file path.
        """
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{exported.template_name.replace(' ', '_')}_{timestamp}.json"
        filepath = Path(output_dir) / filename

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(exported.dict(), f, indent=2, ensure_ascii=False)

        return str(filepath)
