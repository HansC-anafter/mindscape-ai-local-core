"""
Workspace Welcome Service

Generates personalized welcome messages and initial suggestions for new workspaces.
"""

import logging
from typing import Tuple, List, Dict

from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.i18n_service import get_i18n_service

logger = logging.getLogger(__name__)


async def _generate_personalized_suggestions(
    workspace: Workspace,
    store: MindscapeStore,
    profile_id: str,
    active_intents: List[Dict[str, str]],
    available_playbooks: List[Dict[str, str]],
    locale: str,
    model_name: str
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
        from backend.app.capabilities.core_llm.services.generate import run as generate_text
        from backend.app.shared.prompt_templates import get_language_name
        from backend.app.capabilities.core_llm.services.generate import _get_language_instruction

        target_language = get_language_name(locale)
        language_instruction = _get_language_instruction(locale)

        # Get user profile for mindscape context
        profile = store.get_profile(profile_id)
        mindscape_context = ""
        if profile:
            # Get recent events for context
            try:
                recent_events = store.get_events_by_workspace(
                    workspace_id=workspace.id,
                    limit=10
                )
                if recent_events:
                    mindscape_context = f"Recent activity: {len(recent_events)} events in this workspace"
            except Exception:
                pass

        system_prompt = f"""You are an onboarding coach for a new workspace. Give the user concrete, ready-to-click starting actions.

Guidelines (must follow all):
- Output 2-4 concise, actionable suggestions (each <= 15 words) in {target_language} ({locale}).
- Lead with a verb and be specific (e.g., \"生成首頁草稿\" 而非 \"可以開始\").
- Prefer referencing available playbooks / capabilities explicitly (含代碼) when relevant.
- If useful, mention uploading/分析檔案、選擇目標、執行特定 playbook、檢視範例等明確行為。
- Avoid模糊/填充語「或許」「maybe」「let's start」「可以開始」等；避免空泛目標。
- No numbered list markers; one suggestion per line.

**CRITICAL:**
{language_instruction}
If nothing relevant, return nothing."""

        user_prompt = f"""Workspace Context:
- Title: {workspace.title}
- Description: {workspace.description or 'No description'}
- Mode: {workspace.mode or 'Not specified'}

Active Goals/Intents:
{chr(10).join([f"- {intent['title']}: {intent['description']}" for intent in active_intents]) if active_intents else "No active intents yet"}

Available Playbooks (include code for actionable refs):
{chr(10).join([f"- {pb['name']} ({pb['playbook_code']}): {pb['description']}" for pb in available_playbooks[:5]]) if available_playbooks else "No specific playbooks detected"}

Context: {mindscape_context or "This is a new workspace"}

Produce 2-4 actionable starter steps (one per line, no numbering), each <= 15 words, verb-led, specific, in {target_language}. If nothing relevant, return empty."""

        result = await generate_text(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.8,
            max_tokens=200,
            locale=locale,
            workspace_id=workspace.id
        )

        suggestions_text = result.get('text', '') if isinstance(result, dict) else str(result)
        if not suggestions_text:
            return []

        # Parse suggestions from text (split by newlines, clean up)
        suggestions = []
        banned_patterns = [
            r"^或許(也)?可以開始",          # meaningless filler zh
            r"^maybe\\s*(we)?\\s*can\\s*start",  # meaningless filler en
            r"^可以開始",                 # vague zh
            r"^start\\s*now\\b",          # vague en
            r"^let'?s\\s*start",          # vague en
        ]
        import re

        for line in suggestions_text.split('\n'):
            line = line.strip()
            # Remove list markers (-, *, 1., etc.)
            line = line.lstrip('- *•1234567890. ').strip()
            if not line or len(line) <= 5:
                continue
            if any(re.search(p, line, re.IGNORECASE) for p in banned_patterns):
                continue
                suggestions.append(line)

        # Limit to 4 suggestions max
        suggestions = suggestions[:4]

        # If everything got filtered out, return empty to avoid showing junk in UI
        if not suggestions:
            logger.info("Welcome suggestions filtered out (empty after sanitization); returning none.")
            return []

        # If we got suggestions, return them; otherwise return empty
        if suggestions:
            logger.info(f"Generated {len(suggestions)} personalized suggestions for workspace {workspace.id}")
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

                    # Use existing language instruction function for consistency
                    from backend.app.capabilities.core_llm.services.generate import _get_language_instruction
                    from backend.app.shared.prompt_templates import get_language_name

                    target_language = get_language_name(locale)
                    language_instruction = _get_language_instruction(locale)

                    system_prompt = f"""You are a helpful AI assistant welcoming a user to their new workspace "{workspace.title}".

Generate a warm, personalized welcome message that:
1. Welcomes the user to the workspace by name
2. Explains what this workspace is for (based on workspace title and description)
3. Mentions available capabilities/playbooks that might be useful
4. References any active intents/goals if they exist
5. Provides clear next steps and guidance
6. Is conversational, friendly, and encouraging

**CRITICAL LANGUAGE REQUIREMENT:**
{language_instruction}
The workspace locale is {locale} ({target_language}), so you MUST respond in {target_language} only.
Do NOT mix languages. Do NOT use English if the locale is not 'en'.

Keep it concise but informative (2-4 paragraphs)."""

                    # Build user prompt - use English as base (following system prompt design principle)
                    # The LLM will respond in the target language based on system prompt instruction
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

Generate a personalized welcome message for this workspace. Remember to respond in {target_language} ({locale}) as specified in the system prompt."""

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
                    # Basic validity: must have some content
                    if not welcome_message or len(welcome_message.strip()) < 10:
                        raise ValueError("LLM generated empty or invalid welcome message")
                    # If content is too short (likely truncated), fall back to i18n baseline
                    if len(welcome_message.strip()) < 40:
                        logger.warning(
                            f"LLM welcome message too short ({len(welcome_message.strip())} chars); falling back to i18n baseline"
                        )
                        welcome_message = i18n.t("workspace", "welcome.new_workspace", workspace_title=workspace.title)

                    # Validate that message is in correct language (basic check)
                    # Use language detection to verify the generated message matches the locale
                    from backend.app.capabilities.core_llm.services.generate import _detect_prompt_language
                    detected_lang = _detect_prompt_language(welcome_message)

                    # Normalize locale for comparison (e.g., "zh-TW" -> "zh-TW", "ja-JP" -> "ja")
                    normalized_locale = locale.split('-')[0] if '-' in locale else locale
                    normalized_detected = detected_lang.split('-')[0] if detected_lang and '-' in detected_lang else detected_lang

                    # Check if detected language matches locale
                    # Allow some flexibility: zh-TW and zh-CN are both valid for zh locales
                    if normalized_locale == "zh":
                        if normalized_detected not in ["zh", "zh-TW", "zh-CN"]:
                            chinese_chars = len([c for c in welcome_message if '\u4e00' <= c <= '\u9fff'])
                            if chinese_chars < max(10, len(welcome_message) * 0.1):
                                logger.warning(f"LLM generated message appears to be in wrong language for locale {locale} (detected: {detected_lang}, only {chinese_chars} Chinese chars), falling back to i18n")
                                raise ValueError("LLM generated message in wrong language")
                    elif normalized_locale == "ja":
                        if normalized_detected != "ja":
                            japanese_chars = len([c for c in welcome_message if '\u3040' <= c <= '\u309F' or '\u30A0' <= c <= '\u30FF' or '\u4E00' <= c <= '\u9FAF'])
                            if japanese_chars < max(10, len(welcome_message) * 0.1):
                                logger.warning(f"LLM generated message appears to be in wrong language for locale {locale} (detected: {detected_lang}, only {japanese_chars} Japanese chars), falling back to i18n")
                                raise ValueError("LLM generated message in wrong language")
                    elif normalized_locale == "ko":
                        if normalized_detected != "ko":
                            korean_chars = len([c for c in welcome_message if '\uAC00' <= c <= '\uD7A3'])
                            if korean_chars < max(10, len(welcome_message) * 0.1):
                                logger.warning(f"LLM generated message appears to be in wrong language for locale {locale} (detected: {detected_lang}, only {korean_chars} Korean chars), falling back to i18n")
                                raise ValueError("LLM generated message in wrong language")
                    elif normalized_locale == "en":
                        # For English, we don't need strict validation (English is the default fallback)
                        # But log if detected language is clearly wrong
                        if detected_lang and normalized_detected not in ["en", None]:
                            logger.debug(f"LLM generated message detected as {detected_lang} for English locale, but allowing it")
                    else:
                        # For other languages, do basic validation
                        if detected_lang and normalized_detected != normalized_locale:
                            logger.warning(f"LLM generated message detected as {detected_lang} for locale {locale}, but allowing it (may be valid)")

                    logger.info(f"Generated LLM welcome message for workspace {workspace.id} in locale {locale}")

                    # Generate personalized suggestions using AI
                    # Based on workspace context, mindscape, and active intents
                    suggestions = await _generate_personalized_suggestions(
                        workspace=workspace,
                        store=store,
                        profile_id=profile_id,
                        active_intents=active_intents,
                        available_playbooks=available_playbooks,
                        locale=locale,
                        model_name=model_name
                    )

                except Exception as e:
                    logger.warning(f"Failed to generate LLM welcome message, falling back to i18n: {e}")
                    welcome_message = i18n.t("workspace", "welcome.new_workspace", workspace_title=workspace.title)
                    # Fallback to empty suggestions if LLM generation fails
                    suggestions = []
            else:
                welcome_message = i18n.t("workspace", "welcome.returning_workspace", workspace_title=workspace.title)
                # For returning users, also generate personalized suggestions
                try:
                    from backend.app.services.system_settings_store import SystemSettingsStore
                    settings_store = SystemSettingsStore()
                    chat_setting = settings_store.get_setting("chat_model")
                    if chat_setting and chat_setting.value:
                        model_name = str(chat_setting.value)
                        active_intents = []
                        try:
                            from backend.app.models.mindscape import IntentStatus
                            intents = store.list_intents(
                                profile_id=profile_id,
                                status=IntentStatus.ACTIVE
                            )
                            active_intents = [{'title': i.title, 'description': i.description or ''} for i in intents[:5]]
                        except Exception:
                            pass

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
                                        'description': metadata.description or ''
                                    })
                        except Exception:
                            pass

                        suggestions = await _generate_personalized_suggestions(
                            workspace=workspace,
                            store=store,
                            profile_id=profile_id,
                            active_intents=active_intents,
                            available_playbooks=available_playbooks,
                            locale=locale,
                            model_name=model_name
                        )
                    else:
                        suggestions = []
                except Exception as e:
                    logger.warning(f"Failed to generate suggestions for returning user: {e}")
                    suggestions = []

            return welcome_message, suggestions
        except Exception as e:
            logger.warning(f"Failed to generate personalized welcome message: {e}")
            i18n = get_i18n_service(default_locale=locale)
            # Return empty suggestions instead of hardcoded ones
            return i18n.t("workspace", "welcome.fallback", workspace_title=workspace.title), []


