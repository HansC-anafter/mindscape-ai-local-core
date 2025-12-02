"""
Core LLM: Generate Service
Basic one-time text generation/rewriting
"""

import logging
from typing import Dict, Any, Optional

from ....shared.llm_utils import build_prompt, call_llm

logger = logging.getLogger(__name__)


async def run(
    prompt: str,
    system_prompt: Optional[str] = None,
    temperature: float = 0.7,
    max_tokens: Optional[int] = None,
    llm_provider: Optional[Any] = None,
    locale: Optional[str] = None,
    target_language: Optional[str] = None,
    workspace_id: Optional[str] = None,
    available_playbooks: Optional[list] = None
) -> Dict[str, Any]:
    """
    Basic one-time text generation/rewriting

    Args:
        prompt: User prompt
        system_prompt: System prompt (optional)
        temperature: Temperature parameter (default 0.7)
        max_tokens: Maximum token count (optional)
        llm_provider: LLM provider object (optional, will be retrieved from profile)
        locale: Locale code (e.g., "zh-TW", "en"). Deprecated: use target_language instead.
        target_language: Target language for output (e.g., "zh-TW", "en", "ja-JP").
                        Primary parameter. Priority: target_language > locale

    Returns:
        Dict containing:
            - text: Generated text
            - usage: Token usage information
    """
    try:
        if not llm_provider:
            from ....services.agent_runner import LLMProviderManager
            from ....services.config_store import ConfigStore
            from ....services.system_settings_store import SystemSettingsStore
            import os

            config_store = ConfigStore()
            config = config_store.get_or_create_config("default-user")

            openai_key = config.agent_backend.openai_api_key or os.getenv("OPENAI_API_KEY")
            anthropic_key = config.agent_backend.anthropic_api_key or os.getenv("ANTHROPIC_API_KEY")
            vertex_api_key = config.agent_backend.vertex_api_key or os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv("VERTEX_API_KEY")
            vertex_project_id = config.agent_backend.vertex_project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("VERTEX_PROJECT_ID")
            vertex_location = config.agent_backend.vertex_location or os.getenv("VERTEX_LOCATION", "us-central1")
            llm_provider = LLMProviderManager(
                openai_key=openai_key,
                anthropic_key=anthropic_key,
                vertex_api_key=vertex_api_key,
                vertex_project_id=vertex_project_id,
                vertex_location=vertex_location
            )

            # Get conversation model from system settings
            # Must be configured by user in settings panel, no fallback allowed
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

            logger.info(f"Using configured conversation model: {model_name}")
            # Note: model_name will be passed to call_llm() via the model parameter

        target_lang = target_language or locale
        enhanced_system_prompt = system_prompt

        if target_lang:
            # Check if prompt is in a different language than target
            # If so, add explicit instruction to translate/respond in target language
            prompt_lang = _detect_prompt_language(system_prompt or prompt)

            if prompt_lang and prompt_lang != target_lang:
                # Prompt is in different language, add translation instruction
                translation_instruction = _get_translation_instruction(
                    source_lang=prompt_lang,
                    target_lang=target_lang
                )
                lang_instruction = _get_language_instruction(target_lang)

                if enhanced_system_prompt:
                    enhanced_system_prompt = f"{enhanced_system_prompt}\n\n{translation_instruction}\n{lang_instruction}"
                else:
                    enhanced_system_prompt = f"{translation_instruction}\n{lang_instruction}"
            else:
                # Same language or unknown, just add language instruction
                lang_instruction = _get_language_instruction(target_lang)
                if enhanced_system_prompt:
                    enhanced_system_prompt = f"{enhanced_system_prompt}\n\n{lang_instruction}"
                else:
                    enhanced_system_prompt = lang_instruction

        # Build messages with better system prompt for workspace context
        # Only add workspace context if no custom system prompt is provided
        if not system_prompt:
            # Use unified workspace context prompt template with language policy
            from ....shared.prompt_templates import build_workspace_context_prompt

            # Use target_lang for language policy if available
            preferred_lang = target_lang if target_lang else None

            workspace_context = build_workspace_context_prompt(
                preferred_language=preferred_lang,
                include_language_policy=bool(preferred_lang),
                workspace_id=workspace_id,
                available_playbooks=available_playbooks
            )

            # If we had enhanced_system_prompt from language detection, append it
            # (This handles the case where prompt language differs from target language)
            if enhanced_system_prompt and enhanced_system_prompt != system_prompt:
                workspace_context = f"{workspace_context}\n\n{enhanced_system_prompt}"
        else:
            workspace_context = enhanced_system_prompt

        # Build messages
        messages = build_prompt(
            system_prompt=workspace_context,
            user_prompt=prompt
        )

        # Get conversation model from system settings
        # Must be configured by user in settings panel, no fallback allowed
        from ....services.system_settings_store import SystemSettingsStore
        settings_store = SystemSettingsStore()
        chat_setting = settings_store.get_setting("chat_model")

        if not chat_setting or not chat_setting.value:
            raise ValueError(
                "LLM model not configured. Please select a model in the system settings panel."
            )

        conversation_model = str(chat_setting.value)
        if not conversation_model or conversation_model.strip() == "":
            raise ValueError(
                "LLM model is empty. Please select a valid model in the system settings panel."
            )

        logger.info(f"Using conversation model from settings: {conversation_model}")
        model_to_use = conversation_model

        # Call LLM
        result = await call_llm(
            messages=messages,
            llm_provider=llm_provider,
            model=model_to_use,
            temperature=temperature,
            max_tokens=max_tokens
        )

        logger.info(f"Generated text ({len(result.get('text', ''))} chars)")

        return result

    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        raise


def _get_language_instruction(locale: str) -> str:
    """Get language instruction for system prompt based on locale"""
    lang_map = {
        "zh-TW": "請使用繁體中文回答。",
        "zh-CN": "請使用簡體中文回答。",
        "en": "Please answer in English.",
        "ja": "日本語で回答してください。",
        "ja-JP": "日本語で回答してください。",
        "ko": "한국어로 답변해 주세요.",
        "de": "Bitte antworten Sie auf Deutsch.",
        "de-DE": "Bitte antworten Sie auf Deutsch.",
        "es": "Por favor responda en español.",
        "es-ES": "Por favor responda en español.",
        "fr": "Veuillez répondre en français.",
        "fr-FR": "Veuillez répondre en français.",
    }
    return lang_map.get(locale, f"Please answer in {locale}.")


def _detect_prompt_language(text: str) -> Optional[str]:
    """
    Detect language of prompt text (simple heuristic)

    Returns:
        Language code (e.g., "en", "zh-TW") or None if unknown
    """
    if not text:
        return None

    # Simple heuristic: check for Chinese characters
    has_chinese = any('\u4e00' <= char <= '\u9fff' for char in text)
    if has_chinese:
        # Check for traditional vs simplified (rough heuristic)
        # Traditional: 請、說、這
        # Simplified: 请、说、这
        if any(char in text for char in ['請', '說', '這', '為', '與']):
            return "zh-TW"
        else:
            return "zh-CN"

    # Check for Japanese
    has_japanese = any('\u3040' <= char <= '\u309f' or '\u30a0' <= char <= '\u30ff' for char in text)
    if has_japanese:
        return "ja"

    # Check for Korean
    has_korean = any('\uac00' <= char <= '\ud7a3' for char in text)
    if has_korean:
        return "ko"

    # Default to English if no special characters
    return "en"


def _get_translation_instruction(source_lang: str, target_lang: str) -> str:
    """Get instruction to translate/adapt prompt from source to target language"""
    lang_names = {
        "en": "English",
        "zh-TW": "Traditional Chinese",
        "zh-CN": "Simplified Chinese",
        "ja": "Japanese",
        "ja-JP": "Japanese",
        "ko": "Korean",
        "de": "German",
        "de-DE": "German",
        "es": "Spanish",
        "es-ES": "Spanish",
        "fr": "French",
        "fr-FR": "French",
    }

    source_name = lang_names.get(source_lang, source_lang)
    target_name = lang_names.get(target_lang, target_lang)

    return f"The following prompt is written in {source_name}. Please understand it and respond in {target_name}."
