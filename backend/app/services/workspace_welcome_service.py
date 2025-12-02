"""
Workspace Welcome Service

Generates personalized welcome messages and initial suggestions for new workspaces.
"""

import logging
from typing import Tuple, List

from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.i18n_service import get_i18n_service

logger = logging.getLogger(__name__)


class WorkspaceWelcomeService:
    """Generate welcome messages and suggestions for workspaces"""

    @staticmethod
    async def generate_welcome_message(
        workspace: Workspace,
        profile_id: str,
        store: MindscapeStore,
        locale: str = "en"
    ) -> Tuple[str, List[str]]:
        """
        Generate welcome message and initial suggestions for a new workspace

        Uses LLM to generate personalized welcome message with workspace namespace,
        intents, and available capabilities for cold start guidance.

        Args:
            workspace: Workspace object
            profile_id: User profile ID
            store: MindscapeStore instance
            locale: Locale for i18n (default: "en")

        Returns:
            (welcome_message, suggestions_list)
        """
        try:
            i18n = get_i18n_service(default_locale=locale)

            profile = store.get_profile(profile_id)
            onboarding_complete = False
            if profile and profile.onboarding_state:
                onboarding_complete = profile.onboarding_state.get('task3_completed', False)

            if not onboarding_complete:
                try:
                    from backend.app.services.conversation.context_builder import ContextBuilder
                    from backend.app.services.conversation.qa_response_generator import QAResponseGenerator
                    from backend.app.services.stores.timeline_items_store import TimelineItemsStore
                    from backend.app.capabilities.core_llm.services.generate import run as generate_text
                    from backend.app.services.system_settings_store import SystemSettingsStore

                    timeline_items_store = TimelineItemsStore(store.db_path)
                    qa_generator = QAResponseGenerator(
                        store=store,
                        timeline_items_store=timeline_items_store,
                        default_locale=locale
                    )

                    from backend.app.services.system_settings_store import SystemSettingsStore
                    settings_store = SystemSettingsStore()
                    chat_setting = settings_store.get_setting("chat_model")

                    if not chat_setting or not chat_setting.value:
                        raise ValueError(
                            "LLM model not configured. Please select a model in the system settings panel."
                        )

                    model_name = str(chat_setting.value)
                    if not model_name or model_name.strip() == "":
                        raise ValueError(
                            "LLM model is empty. Please select a valid model in the system settings panel."
                        )

                    context_builder = ContextBuilder(
                        store=store,
                        timeline_items_store=timeline_items_store,
                        model_name=model_name
                    )
                    context = await context_builder.build_qa_context(
                        workspace_id=workspace.id,
                        message="",
                        profile_id=profile_id,
                        workspace=workspace,
                        hours=0
                    )

                    available_playbooks = []
                    try:
                        from backend.app.services.playbook_loader import PlaybookLoader
                        playbook_loader = PlaybookLoader()
                        file_playbooks = playbook_loader.load_all_playbooks()

                        for pb in file_playbooks:
                            metadata = pb.metadata if hasattr(pb, 'metadata') else None
                            if metadata and metadata.playbook_code:
                                available_playbooks.append({
                                    'playbook_code': metadata.playbook_code,
                                    'name': metadata.name,
                                    'description': metadata.description or '',
                                    'tags': metadata.tags or []
                                })
                    except Exception as e:
                        logger.debug(f"Could not load playbooks for welcome message: {e}")

                    active_intents = []
                    try:
                        from backend.app.models.mindscape import IntentStatus
                        intents = store.list_intents(
                            profile_id=profile_id,
                            status=IntentStatus.ACTIVE
                        )
                        active_intents = [{'title': i.title, 'description': i.description or ''} for i in intents[:5]]
                    except Exception as e:
                        logger.debug(f"Could not load intents for welcome message: {e}")

                    system_prompt = f"""You are a helpful AI assistant welcoming a user to their new workspace "{workspace.title}".

Generate a warm, personalized welcome message that:
1. Welcomes the user to the workspace by name
2. Explains what this workspace is for (based on workspace title and description)
3. Mentions available capabilities/playbooks that might be useful
4. References any active intents/goals if they exist
5. Provides clear next steps and guidance
6. Is conversational, friendly, and encouraging
7. Uses the workspace's language/locale ({locale})

Keep it concise but informative (2-4 paragraphs)."""

                    user_prompt = f"""Workspace Information:
- Title: {workspace.title}
- Description: {workspace.description or 'No description'}
- Mode: {workspace.mode or 'Not specified'}

Available Capabilities/Playbooks:
{chr(10).join([f"- {pb['name']} ({pb['playbook_code']}): {pb['description']}" for pb in available_playbooks[:10]]) if available_playbooks else "No specific playbooks configured yet"}

Active Goals/Intents:
{chr(10).join([f"- {intent['title']}: {intent['description']}" for intent in active_intents]) if active_intents else "No active intents yet - this is a fresh start!"}

Context:
{context if context else "This is a brand new workspace with no history yet."}

Generate a personalized welcome message for this workspace."""

                    settings_store = SystemSettingsStore()
                    chat_setting = settings_store.get_setting("chat_model")

                    if not chat_setting or not chat_setting.value:
                        raise ValueError(
                            "LLM model not configured. Please select a model in the system settings panel."
                        )

                    model_name = str(chat_setting.value)
                    if not model_name or model_name.strip() == "":
                        raise ValueError(
                            "LLM model is empty. Please select a valid model in the system settings panel."
                        )

                    result = await generate_text(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        temperature=0.7,
                        max_tokens=500,
                        locale=locale,
                        workspace_id=workspace.id,
                        available_playbooks=available_playbooks
                    )
                    welcome_message = result.get('text', '') if isinstance(result, dict) else str(result)
                    if not welcome_message or len(welcome_message.strip()) < 10:
                        raise ValueError("LLM generated empty or invalid welcome message")

                    logger.info(f"Generated LLM welcome message for workspace {workspace.id}")

                except Exception as e:
                    logger.warning(f"Failed to generate LLM welcome message, falling back to i18n: {e}")
                    welcome_message = i18n.t("workspace", "welcome.new_workspace", workspace_title=workspace.title)
            else:
                welcome_message = i18n.t("workspace", "welcome.returning_workspace", workspace_title=workspace.title)

            suggestions = [
                i18n.t("workspace", "suggestions.organize_tasks"),
                i18n.t("workspace", "suggestions.daily_planning"),
                i18n.t("workspace", "suggestions.view_progress")
            ]

            if workspace.default_playbook_id:
                try:
                    from ...services.playbook_loader import PlaybookLoader
                    loader = PlaybookLoader()
                    playbook = loader.get_playbook_by_code(workspace.default_playbook_id)
                    if playbook:
                        suggestions.insert(0, i18n.t("workspace", "suggestions.execute_playbook", playbook_name=playbook.metadata.name))
                except Exception:
                    suggestions.insert(0, i18n.t("workspace", "suggestions.execute_playbook", playbook_name=workspace.default_playbook_id))

            return welcome_message, suggestions
        except Exception as e:
            logger.warning(f"Failed to generate personalized welcome message: {e}")
            i18n = get_i18n_service(default_locale=locale)
            return i18n.t("workspace", "welcome.fallback", workspace_title=workspace.title), [
                i18n.t("workspace", "suggestions.organize_tasks"),
                i18n.t("workspace", "suggestions.daily_planning")
            ]

