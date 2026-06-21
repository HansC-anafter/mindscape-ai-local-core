"""Language policy prompt helpers."""


_LANGUAGE_NAMES = {
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


def get_language_name(locale: str) -> str:
    """
    Get human-readable language name for a locale code

    Args:
        locale: Locale code (e.g., "zh-TW", "en", "ja-JP")

    Returns:
        Human-readable language name (e.g., "Traditional Chinese", "English")
    """
    return _LANGUAGE_NAMES.get(locale, locale)


def build_language_policy_section(preferred_language: str) -> str:
    """
    Build language policy section for system prompt

    This section should be injected into system prompts to tell the LLM
    what language to use for responses. The policy is written in English
    (following the design principle that system prompts should be in English
    as the base), but instructs the LLM to respond in the user's preferred language.

    Args:
        preferred_language: User's preferred language (e.g., "zh-TW", "en", "ja")

    Returns:
        Language policy section string to be included in system prompt
    """
    language_name = get_language_name(preferred_language)

    return f"""[LANGUAGE_POLICY]
User's preferred language: {preferred_language} ({language_name}).

Rules:
1. By default, reply in the user's preferred language ({language_name}).
2. If the user explicitly asks to switch language (e.g., "請改用英文回答" or "Please respond in English"), obey the user's request.
3. For code, API names, and identifiers, keep them in English unless the user explicitly requests otherwise.
[/LANGUAGE_POLICY]"""
