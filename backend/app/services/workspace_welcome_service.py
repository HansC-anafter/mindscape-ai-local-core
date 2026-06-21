"""
Workspace Welcome Service

Generates personalized welcome messages and initial suggestions for new workspaces.
"""

import logging
from typing import Tuple, List, Dict

from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.i18n_service import get_i18n_service
from backend.app.services.workspace_welcome_core import (
    build_suggestions_system_prompt,
    build_suggestions_user_prompt,
    build_welcome_system_prompt,
    build_welcome_user_prompt,
    sanitize_suggestions_text,
    validate_welcome_message_locale,
)

logger = logging.getLogger(__name__)


async def _generate_personalized_suggestions(
    workspace: Workspace,
    store: MindscapeStore,
    profile_id: str,
    active_intents: List[Dict[str, str]],
    available_playbooks: List[Dict[str, str]],
    locale: str,
    model_name: str,
) -> List[str]:
    """
    Generate personalized suggestions using AI based on workspace context

    Args:
        workspace: Workspace object
        store: MindscapeStore instance
        profile_id: User profile ID
        active_intents: List of active intents
        available_playbooks: List of available playbooks
        locale: Locale for i18n
        model_name: LLM model name

    Returns:
        List of suggestion strings (2-4 suggestions, natural and gentle)
    """
    try:
        from backend.app.capabilities.core_llm.services.generate import (
            run as generate_text,
        )
        from backend.app.shared.prompt_templates import get_language_name
        from backend.app.capabilities.core_llm.services.generate import (
            _get_language_instruction,
        )

        target_language = get_language_name(locale)
        language_instruction = _get_language_instruction(locale)

        # Get user profile for mindscape context
        profile = store.get_profile(profile_id)
        mindscape_context = ""
        if profile:
            # Get recent events for context
            try:
                recent_events = store.get_events_by_workspace(
                    workspace_id=workspace.id, limit=10
                )
                if recent_events:
                    mindscape_context = f"Recent activity: {len(recent_events)} events in this workspace"
            except Exception:
                pass

        system_prompt = build_suggestions_system_prompt(
            target_language=target_language,
            locale=locale,
            language_instruction=language_instruction,
        )

        # Inject workspace instruction
        from backend.app.services.workspace_instruction_helper import (
            build_workspace_instruction_block,
        )

        ws_block, _src = build_workspace_instruction_block(
            workspace, caller="welcome_suggestions"
        )
        if ws_block:
            system_prompt = ws_block + "\n\n" + system_prompt

        user_prompt = build_suggestions_user_prompt(
            workspace=workspace,
            active_intents=active_intents,
            available_playbooks=available_playbooks,
            mindscape_context=mindscape_context,
            target_language=target_language,
        )

        result = await generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.8,
            max_tokens=200,
            locale=locale,
            workspace_id=workspace.id,
        )

        suggestions_text = (
            result.get("text", "") if isinstance(result, dict) else str(result)
        )
        if not suggestions_text:
            return []

        suggestions = sanitize_suggestions_text(suggestions_text)

        # If everything got filtered out, return empty to avoid showing junk in UI
        if not suggestions:
            logger.info(
                "Welcome suggestions filtered out (empty after sanitization); returning none."
            )
            return []

        # If we got suggestions, return them; otherwise return empty
        if suggestions:
            logger.info(
                f"Generated {len(suggestions)} personalized suggestions for workspace {workspace.id}"
            )
            return suggestions
        else:
            logger.warning(f"Failed to parse suggestions from LLM response")
            return []

    except Exception as e:
        logger.warning(f"Failed to generate personalized suggestions: {e}")
        return []


class WorkspaceWelcomeService:
    """Generate welcome messages and suggestions for workspaces"""

    @staticmethod
    async def generate_welcome_message(
        workspace: Workspace, profile_id: str, store: MindscapeStore, locale: str = "en"
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
                onboarding_complete = profile.onboarding_state.get(
                    "task3_completed", False
                )

            if not onboarding_complete:
                try:
                    from backend.app.services.conversation.context_builder import (
                        ContextBuilder,
                    )
                    from backend.app.services.conversation.qa_response_generator import (
                        QAResponseGenerator,
                    )
                    from backend.app.services.stores.postgres.timeline_items_store import (
                        PostgresTimelineItemsStore,
                    )
                    from backend.app.capabilities.core_llm.services.generate import (
                        run as generate_text,
                    )
                    from backend.app.shared.llm_provider_helper import (
                        get_model_name_from_chat_model,
                    )

                    timeline_items_store = PostgresTimelineItemsStore()
                    qa_generator = QAResponseGenerator(
                        store=store,
                        timeline_items_store=timeline_items_store,
                        default_locale=locale,
                    )

                    model_name = get_model_name_from_chat_model()
                    if not model_name:
                        raise ValueError(
                            "LLM model not configured in model-routing-registry."
                        )
                    if not model_name or model_name.strip() == "":
                        raise ValueError(
                            "LLM model is empty. Configure chat_model in model-routing-registry."
                        )

                    context_builder = ContextBuilder(
                        store=store,
                        timeline_items_store=timeline_items_store,
                        model_name=model_name,
                    )
                    context = await context_builder.build_qa_context(
                        workspace_id=workspace.id,
                        message="",
                        profile_id=profile_id,
                        workspace=workspace,
                        hours=0,
                    )

                    available_playbooks = []
                    try:
                        from backend.app.services.playbook_loader import PlaybookLoader

                        playbook_loader = PlaybookLoader()
                        file_playbooks = playbook_loader.load_all_playbooks()

                        for pb in file_playbooks:
                            metadata = pb.metadata if hasattr(pb, "metadata") else None
                            if metadata and metadata.playbook_code:
                                available_playbooks.append(
                                    {
                                        "playbook_code": metadata.playbook_code,
                                        "name": metadata.name,
                                        "description": metadata.description or "",
                                        "tags": metadata.tags or [],
                                    }
                                )
                    except Exception as e:
                        logger.debug(
                            f"Could not load playbooks for welcome message: {e}"
                        )

                    active_intents = []
                    try:
                        from backend.app.models.mindscape import IntentStatus

                        intents = store.list_intents(
                            profile_id=profile_id, status=IntentStatus.ACTIVE
                        )
                        active_intents = [
                            {"title": i.title, "description": i.description or ""}
                            for i in intents[:5]
                        ]
                    except Exception as e:
                        logger.debug(f"Could not load intents for welcome message: {e}")

                    # Use existing language instruction function for consistency
                    from backend.app.capabilities.core_llm.services.generate import (
                        _get_language_instruction,
                    )
                    from backend.app.shared.prompt_templates import get_language_name

                    target_language = get_language_name(locale)
                    language_instruction = _get_language_instruction(locale)

                    system_prompt = build_welcome_system_prompt(
                        workspace=workspace,
                        locale=locale,
                        target_language=target_language,
                        language_instruction=language_instruction,
                    )

                    # Inject workspace instruction
                    from backend.app.services.workspace_instruction_helper import (
                        build_workspace_instruction_block,
                    )

                    ws_block, _src = build_workspace_instruction_block(
                        workspace, caller="welcome_message"
                    )
                    if ws_block:
                        system_prompt = ws_block + "\n\n" + system_prompt

                    user_prompt = build_welcome_user_prompt(
                        workspace=workspace,
                        available_playbooks=available_playbooks,
                        active_intents=active_intents,
                        context=context,
                        target_language=target_language,
                        locale=locale,
                    )

                    model_name = get_model_name_from_chat_model()
                    if not model_name:
                        raise ValueError(
                            "LLM model not configured in model-routing-registry."
                        )
                    if not model_name or model_name.strip() == "":
                        raise ValueError(
                            "LLM model is empty. Configure chat_model in model-routing-registry."
                        )

                    result = await generate_text(
                        prompt=user_prompt,
                        system_prompt=system_prompt,
                        temperature=0.7,
                        max_tokens=2000,
                        locale=locale,
                        workspace_id=workspace.id,
                        available_playbooks=available_playbooks,
                    )
                    welcome_message = (
                        result.get("text", "")
                        if isinstance(result, dict)
                        else str(result)
                    )
                    # Basic validity: must have some content
                    if not welcome_message or len(welcome_message.strip()) < 10:
                        raise ValueError(
                            "LLM generated empty or invalid welcome message"
                        )
                    # If content is too short (likely truncated), fall back to i18n baseline
                    # Reduced threshold from 40 to 20 to allow shorter but valid messages
                    if len(welcome_message.strip()) < 20:
                        logger.warning(
                            f"LLM welcome message too short ({len(welcome_message.strip())} chars); falling back to i18n baseline"
                        )
                        welcome_message = i18n.t(
                            "workspace",
                            "welcome.new_workspace",
                            workspace_title=workspace.title,
                        )

                    # Validate that message is in correct language (basic check)
                    # Use language detection to verify the generated message matches the locale
                    from backend.app.capabilities.core_llm.services.generate import (
                        _detect_prompt_language,
                    )

                    detected_lang = _detect_prompt_language(welcome_message)

                    validation = validate_welcome_message_locale(
                        welcome_message=welcome_message,
                        locale=locale,
                        detected_lang=detected_lang,
                    )
                    if validation.message and validation.log_level == "debug":
                        logger.debug(validation.message)
                    elif validation.message:
                        logger.warning(validation.message)
                    if not validation.is_valid:
                        raise ValueError(
                            validation.error
                            or "LLM generated message in wrong language"
                        )

                    logger.info(
                        f"Generated LLM welcome message for workspace {workspace.id} in locale {locale}"
                    )

                    # Generate personalized suggestions using AI
                    # Based on workspace context, mindscape, and active intents
                    suggestions = await _generate_personalized_suggestions(
                        workspace=workspace,
                        store=store,
                        profile_id=profile_id,
                        active_intents=active_intents,
                        available_playbooks=available_playbooks,
                        locale=locale,
                        model_name=model_name,
                    )

                except Exception as e:
                    logger.warning(
                        f"Failed to generate LLM welcome message, falling back to i18n: {e}"
                    )
                    welcome_message = i18n.t(
                        "workspace",
                        "welcome.new_workspace",
                        workspace_title=workspace.title,
                    )
                    # Fallback to empty suggestions if LLM generation fails
                    suggestions = []
            else:
                welcome_message = i18n.t(
                    "workspace",
                    "welcome.returning_workspace",
                    workspace_title=workspace.title,
                )
                # For returning users, also generate personalized suggestions
                try:
                    from backend.app.shared.llm_provider_helper import (
                        get_model_name_from_chat_model,
                    )

                    model_name = get_model_name_from_chat_model()
                    if model_name:
                        active_intents = []
                        try:
                            from backend.app.models.mindscape import IntentStatus

                            intents = store.list_intents(
                                profile_id=profile_id, status=IntentStatus.ACTIVE
                            )
                            active_intents = [
                                {"title": i.title, "description": i.description or ""}
                                for i in intents[:5]
                            ]
                        except Exception:
                            pass

                        available_playbooks = []
                        try:
                            from backend.app.services.playbook_loader import (
                                PlaybookLoader,
                            )

                            playbook_loader = PlaybookLoader()
                            file_playbooks = playbook_loader.load_all_playbooks()
                            for pb in file_playbooks:
                                metadata = (
                                    pb.metadata if hasattr(pb, "metadata") else None
                                )
                                if metadata and metadata.playbook_code:
                                    available_playbooks.append(
                                        {
                                            "playbook_code": metadata.playbook_code,
                                            "name": metadata.name,
                                            "description": metadata.description or "",
                                        }
                                    )
                        except Exception:
                            pass

                        suggestions = await _generate_personalized_suggestions(
                            workspace=workspace,
                            store=store,
                            profile_id=profile_id,
                            active_intents=active_intents,
                            available_playbooks=available_playbooks,
                            locale=locale,
                            model_name=model_name,
                        )
                    else:
                        suggestions = []
                except Exception as e:
                    logger.warning(
                        f"Failed to generate suggestions for returning user: {e}"
                    )
                    suggestions = []

            return welcome_message, suggestions
        except Exception as e:
            logger.warning(f"Failed to generate personalized welcome message: {e}")
            i18n = get_i18n_service(default_locale=locale)
            # Return empty suggestions instead of hardcoded ones
            return (
                i18n.t(
                    "workspace", "welcome.fallback", workspace_title=workspace.title
                ),
                [],
            )
