"""
Dynamic Suggestion Generator Service
Generates context-aware suggestions based on installed capability packs, playbooks, and workspace state
"""

import logging
from typing import Dict, Any, List, Optional
from datetime import datetime

from backend.app.capabilities.registry import get_registry
from backend.app.services.playbook_service import PlaybookService
from backend.app.services.conversation.plan_builder import PlanBuilder
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class SuggestionGenerator:
    """Generate dynamic suggestions based on installed capabilities and workspace context"""

    def __init__(
        self,
        store: Optional[MindscapeStore] = None,
        plan_builder: Optional[PlanBuilder] = None,
        default_locale: str = "zh-TW",
        playbook_service: Optional[PlaybookService] = None
    ):
        self.store = store or MindscapeStore()
        self.default_locale = default_locale
        self.plan_builder = plan_builder or PlanBuilder(store=self.store, default_locale=default_locale)
        self.registry = get_registry()
        self.playbook_service = playbook_service or PlaybookService(store=self.store)
        from backend.app.services.i18n_service import get_i18n_service
        self.i18n = get_i18n_service(default_locale=default_locale)
        from backend.app.services.config_store import ConfigStore
        self.config_store = ConfigStore(db_path=self.store.db_path)

    async def generate_suggestions(
        self,
        workspace_id: str,
        profile_id: str,
        context: Dict[str, Any],
        locale: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Generate dynamic suggestions based on:
        - Installed capability packs
        - Available playbooks
        - Workspace context (recent files, intents, mode)
        - Tool configuration status

        Args:
            workspace_id: Workspace ID
            profile_id: Profile ID
            context: Workspace context (from WorkbenchService)

        Returns:
            List of suggestion objects with:
            - title: Suggestion title
            - description: Suggestion description
            - action: Action type (e.g., 'execute_playbook', 'use_tool', 'create_intent')
            - params: Action parameters
            - cta_label: Button label
            - priority: 'high', 'medium', 'low'
            - side_effect_level: 'readonly', 'soft_write', 'hard_write'
        """
        try:
            suggestions = []

            installed_packs = self._get_installed_packs()
            logger.info(f"Found {len(installed_packs)} installed packs")

            # Get locale from context or use default
            target_locale = locale or self.default_locale
            available_playbooks = await self._get_available_playbooks(locale=target_locale)
            logger.info(f"Found {len(available_playbooks)} available playbooks (locale: {target_locale})")

            has_recent_file = bool(context.get("recent_file"))
            has_intents = bool(context.get("detected_intents") and len(context.get("detected_intents", [])) > 0)
            workspace_focus = context.get("workspace_focus")

            context['workspace_id'] = workspace_id

            if has_recent_file:
                file_suggestions = self._generate_file_suggestions(
                    context, installed_packs, available_playbooks
                )
                suggestions.extend(file_suggestions)

            intent_suggestions = self._generate_intent_suggestions(
                context, installed_packs, available_playbooks, has_intents
            )
            suggestions.extend(intent_suggestions)

            playbook_suggestions = await self._generate_playbook_suggestions(
                context, installed_packs, available_playbooks, workspace_id, profile_id
            )
            suggestions.extend(playbook_suggestions)

            pack_suggestions = self._generate_pack_suggestions(
                context, installed_packs
            )
            suggestions.extend(pack_suggestions)

            if len(suggestions) == 0:
                suggestions.extend(self._generate_fallback_suggestions())

            suggestions.sort(key=lambda s: self._priority_score(s.get("priority", "low")))
            return suggestions[:3]

        except Exception as e:
            logger.error(f"Failed to generate suggestions: {e}", exc_info=True)
            return self._generate_fallback_suggestions()

    def _get_installed_packs(self) -> List[Dict[str, Any]]:
        """Get list of installed capability packs with metadata"""
        try:
            import sqlite3
            import os
            import json

            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
                "data", "mindscape.db"
            )

            if not os.path.exists(db_path):
                return []

            installed_packs = []
            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT pack_id, metadata FROM installed_packs')
                for row in cursor.fetchall():
                    pack_id = row['pack_id']
                    metadata_str = row['metadata']
                    metadata = json.loads(metadata_str) if metadata_str else {}

                    capability_info = self.registry.capabilities.get(pack_id)
                    if capability_info:
                        manifest = capability_info.get('manifest', {})
                        side_effect_level = manifest.get('side_effect_level', 'readonly')
                        tools_configured = self.plan_builder.check_pack_tools_configured(pack_id)

                        installed_packs.append({
                            'pack_id': pack_id,
                            'manifest': manifest,
                            'side_effect_level': side_effect_level,
                            'tools_configured': tools_configured,
                            'display_name': manifest.get('display_name', pack_id),
                            'description': manifest.get('description', ''),
                            'tools': manifest.get('tools', [])
                        })

            return installed_packs
        except Exception as e:
            logger.warning(f"Failed to get installed packs: {e}")
            return []

    async def _get_available_playbooks(self, locale: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get list of available playbooks, filtered by locale if specified"""
        try:
            import asyncio

            # Use PlaybookService to get playbooks
            target_locale = locale or self.default_locale
            playbook_metadata_list = await self.playbook_service.list_playbooks(
                workspace_id=None,  # Get all playbooks
                locale=target_locale,
                category=None,
                source=None,
                tags=None
            )

            # Convert PlaybookMetadata to dict format
            return [
                {
                    'playbook_code': pb.playbook_code,
                    'name': pb.name,
                    'description': pb.description or '',
                    'tags': pb.tags or [],
                    'tool_dependencies': pb.tool_dependencies or []
                }
                for pb in playbook_metadata_list
            ]
        except Exception as e:
            logger.warning(f"Failed to get available playbooks: {e}")
            return []

    def _generate_file_suggestions(
        self,
        context: Dict[str, Any],
        installed_packs: List[Dict[str, Any]],
        available_playbooks: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate suggestions based on recent file"""
        suggestions = []

        recent_file = context.get("recent_file", {})
        file_name = recent_file.get("name", "")

        if any("grant" in pb['playbook_code'].lower() or "government" in pb['playbook_code'].lower()
               for pb in available_playbooks):
            grant_playbook = next(
                (pb for pb in available_playbooks
                 if "grant" in pb['playbook_code'].lower() or "government" in pb['playbook_code'].lower()),
                None
            )
            if grant_playbook:
                suggestions.append({
                    'title': f"Process {file_name}",
                    'description': f"Use {grant_playbook['name']} to process this document",
                    'action': 'execute_playbook',
                    'params': {
                        'playbook_code': grant_playbook['playbook_code'],
                        'file_name': file_name
                    },
                    'cta_label': 'Process Document',
                    'priority': 'high',
                    'side_effect_level': 'readonly'
                })

        if any("proposal" in pb['playbook_code'].lower() or "major" in pb['playbook_code'].lower()
               for pb in available_playbooks):
            proposal_playbook = next(
                (pb for pb in available_playbooks
                 if "proposal" in pb['playbook_code'].lower() or "major" in pb['playbook_code'].lower()),
                None
            )
            if proposal_playbook and file_name.lower().endswith(('.pdf', '.docx', '.doc')):
                suggestions.append({
                    'title': f"Analyze {file_name}",
                    'description': f"Extract structure and create proposal from {file_name}",
                    'action': 'execute_playbook',
                    'params': {
                        'playbook_code': proposal_playbook['playbook_code'],
                        'file_name': file_name
                    },
                    'cta_label': 'Create Proposal',
                    'priority': 'high',
                    'side_effect_level': 'soft_write'
                })

        if file_name.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg')):
            suggestions.append({
                'title': f"Extract text from {file_name}",
                'description': 'Use OCR to extract text from scanned document',
                'action': 'use_tool',
                'params': {
                    'tool': 'core_files.extract_text',
                    'file_path': file_name
                },
                'cta_label': 'Extract Text',
                'priority': 'medium',
                'side_effect_level': 'readonly'
            })

        return suggestions

    def _generate_intent_suggestions(
        self,
        context: Dict[str, Any],
        installed_packs: List[Dict[str, Any]],
        available_playbooks: List[Dict[str, Any]],
        has_intents: bool
    ) -> List[Dict[str, Any]]:
        """Generate suggestions based on intents"""
        suggestions = []

        if not has_intents:
            suggestions.append({
                'title': self.i18n.t("conversation_orchestrator", "suggestion.create_intent_card_title"),
                'description': self.i18n.t("conversation_orchestrator", "suggestion.create_intent_card_description"),
                'action': 'create_intent',
                'params': {},
                'cta_label': self.i18n.t("conversation_orchestrator", "suggestion.create_intent_card_cta"),
                'priority': 'medium',
                'side_effect_level': 'soft_write'
            })
        else:
            daily_planning_pack = next(
                (p for p in installed_packs if p['pack_id'] == 'daily_planning'),
                None
            )
            if daily_planning_pack and daily_planning_pack.get('tools_configured'):
                suggestions.append({
                    'title': self.i18n.t("conversation_orchestrator", "suggestion.organize_tasks_title"),
                    'description': self.i18n.t("conversation_orchestrator", "suggestion.organize_tasks_description"),
                    'action': 'use_tool',
                    'params': {
                        'tool': 'daily_planning.extract_tasks',
                        'workspace_id': context.get('workspace_id')
                    },
                    'cta_label': self.i18n.t("conversation_orchestrator", "suggestion.organize_tasks_cta"),
                    'priority': 'high',
                    'side_effect_level': 'soft_write'
                })

        return suggestions

    async def _generate_playbook_suggestions(
        self,
        context: Dict[str, Any],
        installed_packs: List[Dict[str, Any]],
        available_playbooks: List[Dict[str, Any]],
        workspace_id: str,
        profile_id: str
    ) -> List[Dict[str, Any]]:
        """
        Generate playbook suggestions using LLM-based semantic analysis

        Mechanism:
        1. LLM analyzes workspace content (timeline items, assistant messages, workspace focus)
        2. LLM identifies content tags and characteristics
        3. LLM suggests relevant playbooks with confidence scores and reasons
        4. No hardcoded keyword matching - pure LLM-driven semantic understanding
        """
        suggestions = []

        # Get recent timeline items (LLM outputs) from context
        recent_timeline_items = context.get("recent_timeline_items", [])
        recent_assistant_messages = context.get("recent_assistant_messages", [])
        workspace_focus = context.get("workspace_focus", "")

        # Use LLM to analyze content and suggest playbooks (pure LLM mechanism)
        try:
            # Get full LLM analysis including content tags
            llm_analysis_result = await self._llm_analyze_and_suggest_playbooks(
                recent_timeline_items,
                recent_assistant_messages,
                workspace_focus,
                available_playbooks,
                workspace_id,
                profile_id
            )

            # Handle both dict (new format) and list (old format) for backward compatibility
            if isinstance(llm_analysis_result, dict):
                llm_suggestions = llm_analysis_result.get("suggested_playbooks", [])
                content_tags = llm_analysis_result.get("content_tags", [])
                analysis_summary = llm_analysis_result.get("analysis_summary", "")
            else:
                # Fallback for old format (list)
                llm_suggestions = llm_analysis_result if isinstance(llm_analysis_result, list) else []
                content_tags = []
                analysis_summary = ""

            # Convert LLM suggestions to suggestion format
            for suggestion in llm_suggestions:
                playbook_code = suggestion.get("playbook_code")
                confidence = suggestion.get("confidence", 0.0)
                reason = suggestion.get("reason", "")
                priority = suggestion.get("priority", "medium")

                # Find matching playbook
                playbook = next((p for p in available_playbooks if p['playbook_code'] == playbook_code), None)
                if playbook and self._check_playbook_tools_available(playbook, installed_packs):
                    playbook_name = playbook.get('name', playbook['playbook_code'])
                    suggestions.append({
                        'title': f"{self.i18n.t('conversation_orchestrator', 'suggestion.run_playbook_cta')} {playbook_name}",
                        'description': playbook.get('description', ''),
                        'action': 'execute_playbook',
                        'params': {
                            'playbook_code': playbook['playbook_code'],
                            'llm_analysis': {
                                'confidence': confidence,
                                'reason': reason,
                                'content_tags': content_tags,  # Include content tags from LLM analysis
                                'analysis_summary': analysis_summary
                            }
                        },
                        'cta_label': self.i18n.t("conversation_orchestrator", "suggestion.run_playbook_cta"),
                        'priority': priority,  # Use LLM-provided priority
                        'side_effect_level': 'readonly',
                        # Include LLM analysis results at top level for frontend
                        'llm_analysis': {
                            'confidence': confidence,
                            'reason': reason,
                            'content_tags': content_tags,  # Include content tags from LLM analysis
                            'analysis_summary': analysis_summary
                        }
                    })

            logger.info(f"LLM suggested {len(suggestions)} playbooks (confidence scores: {[s.get('confidence', 0) for s in llm_suggestions]}, content_tags: {content_tags})")
        except Exception as e:
            logger.error(f"LLM playbook analysis failed: {e}", exc_info=True)
            # No fallback - if LLM fails, return empty (fail fast, no degradation)
            return []

        return suggestions


    def _check_playbook_tools_available(
        self,
        playbook: Dict[str, Any],
        installed_packs: List[Dict[str, Any]]
    ) -> bool:
        """Check if all required tools for a playbook are available"""
        tool_deps = playbook.get('tool_dependencies', [])
        if not tool_deps:
            return True  # No dependencies, assume available

        for tool_dep in tool_deps:
            tool_name = tool_dep.split('.')[-1] if '.' in tool_dep else tool_dep
            capability_code = tool_dep.split('.')[0] if '.' in tool_dep else None

            tool_available = any(
                any(t.get('name') == tool_name for t in pack.get('tools', []))
                for pack in installed_packs
                if not capability_code or pack['pack_id'] == capability_code
            )

            if not tool_available:
                registry_tool = self.registry.get_tool(tool_dep)
                tool_available = registry_tool is not None

            if not tool_available:
                return False

        return True

    async def _llm_analyze_and_suggest_playbooks(
        self,
        timeline_items: List[Dict[str, Any]],
        assistant_messages: List[Dict[str, Any]],
        workspace_focus: str,
        available_playbooks: List[Dict[str, Any]],
        workspace_id: str,
        profile_id: str
    ) -> Dict[str, Any]:
        """
        Use LLM to analyze content and suggest relevant playbooks with confidence scores

        Returns dict with:
        - suggested_playbooks: List of playbook suggestions with:
          - playbook_code: Suggested playbook code
          - confidence: Confidence score (0.0-1.0)
          - reason: Why this playbook is suggested
          - priority: "high", "medium", or "low"
        - content_tags: List of content characteristics identified
        - analysis_summary: Brief summary of what user is working on
        """
        try:
            from backend.app.capabilities.core_llm.services.structured import extract
            from backend.app.services.agent_runner import LLMProviderManager
            import os
            import json

            # Get LLM API keys from user config
            config = self.config_store.get_or_create_config(profile_id)
            openai_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            anthropic_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
            vertex_api_key = config.agent_backend.vertex_api_key or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("VERTEX_API_KEY")
            vertex_project_id = config.agent_backend.vertex_project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT_ID")
            vertex_location = config.agent_backend.vertex_location or os.getenv("VERTEX_LOCATION", "us-central1")

            llm_manager = LLMProviderManager(
                openai_key=openai_key,
                anthropic_key=anthropic_key,
                vertex_api_key=vertex_api_key,
                vertex_project_id=vertex_project_id,
                vertex_location=vertex_location
            )

            # Get user's selected chat model to determine provider
            from backend.app.services.system_settings_store import SystemSettingsStore
            settings_store = SystemSettingsStore()
            chat_setting = settings_store.get_setting("chat_model")
            provider_name = None

            if chat_setting:
                # Get provider from model metadata or infer from model name
                provider_name = chat_setting.metadata.get("provider")
                if not provider_name:
                    model_name = str(chat_setting.value)
                    # Infer provider from model name
                    if "gemini" in model_name.lower():
                        provider_name = "vertex-ai"
                    elif "gpt" in model_name.lower() or "text-" in model_name.lower():
                        provider_name = "openai"
                    elif "claude" in model_name.lower():
                        provider_name = "anthropic"

            # Get provider based on user's selection - no fallback
            if not provider_name:
                error_msg = "Cannot determine LLM provider: chat_model not configured in system settings"
                logger.error(error_msg)
                raise ValueError(error_msg)

            llm_provider = llm_manager.get_provider(provider_name)
            if not llm_provider:
                model_name = str(chat_setting.value) if chat_setting and chat_setting.value else "unknown"
                error_msg = f"Provider '{provider_name}' not available for model '{model_name}'. Please check your API configuration."
                logger.error(error_msg)
                raise ValueError(error_msg)

            # Build content summary for analysis
            content_summary = self._build_content_summary(
                timeline_items,
                assistant_messages,
                workspace_focus
            )

            # Build playbook list for reference
            playbook_list = "\n".join([
                f"- {pb['playbook_code']}: {pb.get('name', '')} - {pb.get('description', '')[:150]}"
                for pb in available_playbooks  # Include all available playbooks
            ])

            # Build analysis prompt - pure LLM semantic analysis, no hardcoded rules
            analysis_text = f"""Analyze the following workspace content and suggest relevant playbooks using semantic understanding.

Workspace Focus: {workspace_focus or "None"}

Recent Timeline Items (LLM Outputs):
{content_summary}

Available Playbooks:
{playbook_list}

Your task (use semantic understanding, NOT keyword matching):
1. Understand what the user is ACTUALLY working on (semantic meaning)
2. Identify content characteristics and tags based on your understanding
3. Match playbooks that would genuinely help the user based on semantic relevance
4. Provide honest confidence scores (0.0-1.0) - only suggest if truly relevant
5. Explain why each playbook is suggested based on semantic analysis

Do NOT use keyword matching. Use your understanding of what the content means and what playbooks would help."""

            schema_description = """Analyze workspace content and suggest relevant playbooks using semantic understanding.

Your task:
1. Understand the SEMANTIC meaning of the content (not keywords)
2. Identify content characteristics and tags (e.g., course content, task structure, timeline tables, product breakdown needs, knowledge organization needs)
3. Match playbooks based on what the user is ACTUALLY working on and what would help them
4. Provide confidence scores (0.0-1.0) - be honest about relevance
5. Explain why each playbook is suggested

Return a structured analysis with:
- content_tags: List of content characteristics you identified (semantic understanding, not keyword matching)
- suggested_playbooks: List of playbook suggestions with confidence scores
- analysis_summary: Brief summary of what the user is working on

Each playbook suggestion should include:
- playbook_code: The playbook code from available playbooks list
- confidence: Confidence score (0.0-1.0) - be honest, only suggest if truly relevant
- reason: Why this playbook is suggested based on semantic content analysis
- priority: "high" (directly relevant), "medium" (somewhat relevant), or "low" (marginally relevant)

Important: Use semantic understanding, not keyword matching. Understand what the user is doing and what playbooks would genuinely help."""

            # No hardcoded example - let LLM analyze freely based on actual content
            # LLM will use semantic understanding to identify tags and suggest playbooks
            example_output = None

            # Extract structured analysis from LLM
            result = await extract(
                text=analysis_text,
                schema_description=schema_description,
                example_output=example_output,
                llm_provider=llm_provider
            )

            extracted_data = result.get("extracted_data", {})
            suggested_playbooks = extracted_data.get("suggested_playbooks", [])
            content_tags = extracted_data.get("content_tags", [])
            analysis_summary = extracted_data.get("analysis_summary", "")

            logger.info(f"LLM analysis identified {len(suggested_playbooks)} playbook suggestions")
            logger.debug(f"Content tags: {content_tags}")
            logger.debug(f"Analysis summary: {analysis_summary}")

            # Return full analysis including content tags
            return {
                "suggested_playbooks": suggested_playbooks,
                "content_tags": content_tags,
                "analysis_summary": analysis_summary
            }

        except Exception as e:
            logger.error(f"Failed to analyze content with LLM: {e}", exc_info=True)
            # Return empty dict (not empty list) to match new return format
            return {"suggested_playbooks": [], "content_tags": [], "analysis_summary": ""}

    def _build_content_summary(
        self,
        timeline_items: List[Dict[str, Any]],
        assistant_messages: List[Dict[str, Any]],
        workspace_focus: str
    ) -> str:
        """Build a summary of content for LLM analysis"""
        parts = []

        if workspace_focus:
            parts.append(f"Workspace Focus: {workspace_focus[:200]}")

        if timeline_items:
            parts.append(f"\nTimeline Items ({len(timeline_items)}):")
            for item in timeline_items[:5]:  # Limit to 5 most recent
                item_type = item.get("type", "unknown")
                title = item.get("title", "")[:100] if item.get("title") else "No title"
                summary = item.get("summary", "")[:150] if item.get("summary") else ""
                parts.append(f"  - {item_type}: {title}")
                if summary:
                    parts.append(f"    Summary: {summary}")

        if assistant_messages:
            parts.append(f"\nRecent Assistant Messages ({len(assistant_messages)}):")
            for msg in assistant_messages[:3]:  # Limit to 3 most recent
                message_text = msg.get("message", "")[:300]  # Limit length
                if message_text:
                    parts.append(f"  - {message_text}")

        return "\n".join(parts) if parts else "No content available"


    def _generate_pack_suggestions(
        self,
        context: Dict[str, Any],
        installed_packs: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Generate suggestions based on installed capability packs"""
        suggestions = []

        workspace_focus = context.get('workspace_focus')

        for pack in installed_packs:
            if not pack.get('tools_configured'):
                continue

            pack_id = pack['pack_id']
            display_name = pack.get('display_name', pack_id)
            description = pack.get('description', '')

            if pack_id == 'content_drafting':
                if workspace_focus:
                    suggestions.append({
                        'title': 'Draft Content',
                        'description': f'Create content draft for: {workspace_focus[:50]}',
                        'action': 'use_tool',
                        'params': {
                            'tool': 'content_drafting.generate',
                            'topic': workspace_focus
                        },
                        'cta_label': 'Draft Content',
                        'priority': 'medium',
                        'side_effect_level': pack.get('side_effect_level', 'readonly')
                    })

            elif pack_id == 'research':
                if workspace_focus:
                    suggestions.append({
                        'title': 'Research Topic',
                        'description': f"Research: {workspace_focus[:50]}",
                        'action': 'use_tool',
                        'params': {
                            'tool': 'research.search',
                            'query': workspace_focus
                        },
                        'cta_label': 'Research',
                        'priority': 'medium',
                        'side_effect_level': 'readonly'
                    })

            elif pack_id == 'semantic_seeds':
                if workspace_focus or context.get('recent_file'):
                    suggestions.append({
                        'title': 'Extract Intent Seeds',
                        'description': 'Extract themes and intents from your content',
                        'action': 'use_tool',
                        'params': {
                            'tool': 'semantic_seeds.extract_seeds',
                            'workspace_id': context.get('workspace_id')
                        },
                        'cta_label': 'Extract Seeds',
                        'priority': 'medium',
                        'side_effect_level': 'readonly'
                    })

        return suggestions

    def _generate_fallback_suggestions(self) -> List[Dict[str, Any]]:
        """Generate fallback suggestions when no specific suggestions available"""
        return [
            {
                'title': self.i18n.t("conversation_orchestrator", "suggestion.start_conversation_title"),
                'description': self.i18n.t("conversation_orchestrator", "suggestion.start_conversation_description"),
                'action': 'start_chat',
                'params': {},
                'cta_label': self.i18n.t("conversation_orchestrator", "suggestion.start_conversation_cta"),
                'priority': 'low',
                'side_effect_level': 'readonly'
            },
            {
                'title': self.i18n.t("conversation_orchestrator", "suggestion.upload_file_title"),
                'description': self.i18n.t("conversation_orchestrator", "suggestion.upload_file_description"),
                'action': 'upload_file',
                'params': {},
                'cta_label': self.i18n.t("conversation_orchestrator", "suggestion.upload_file_cta"),
                'priority': 'low',
                'side_effect_level': 'readonly'
            }
        ]

    def _priority_score(self, priority: str) -> int:
        """Convert priority to numeric score for sorting"""
        scores = {'high': 3, 'medium': 2, 'low': 1}
        return scores.get(priority, 0)

