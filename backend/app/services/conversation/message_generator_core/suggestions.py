"""Suggestion message generation helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.capabilities.core_llm.services.generate import run as llm_generate
from backend.app.services.i18n_service import I18nService

logger = logging.getLogger(__name__)


def suggestion_fallback(generator: Any, locale: Optional[str]) -> str:
    i18n = I18nService(default_locale=locale or generator.default_locale)
    return i18n.t("conversation_orchestrator", "suggestion.add_to_mindscape")


async def generate_suggestion_message(
    *,
    generator: Any,
    pack_id: str,
    task_result: Dict[str, Any],
    timeline_item: Dict[str, Any],
    locale: Optional[str] = None,
) -> str:
    """Generate natural suggestion message for soft-write tasks."""
    try:
        provider = generator._ensure_llm_provider()
        if not provider:
            return suggestion_fallback(generator, locale)

        title = timeline_item.get("title", "")
        summary = timeline_item.get("summary", "")
        data = timeline_item.get("data", {})
        result_summary = task_result.get("message") or task_result.get("summary", "")
        context = f"""Pack: {pack_id}
Title: {title}
Summary: {summary or result_summary}"""

        if isinstance(data, dict):
            key_info = []
            intents = data.get("intents", [])
            if isinstance(intents, list) and intents:
                key_info.append(f"Found {len(intents)} intent(s)")
            tasks = data.get("tasks", [])
            if isinstance(tasks, list) and tasks:
                key_info.append(f"Found {len(tasks)} task(s)")
            if key_info:
                context += f"\nKey findings: {', '.join(key_info)}"

        system_prompt = """You are a helpful AI assistant suggesting actions to users.

Generate a brief, natural suggestion message that:
1. Explains what was found or extracted
2. Suggests adding it to the user's workspace (intents, tasks, etc.)
3. Is friendly and encouraging
4. Is concise (1-2 sentences)

Do not use generic greetings. Be direct and helpful."""
        user_prompt = f"""The following content has been extracted:

{context}

Generate a natural suggestion message encouraging the user to add this to their workspace."""

        result = await llm_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            llm_provider=provider,
            target_language=locale or generator.default_locale,
        )
        suggestion = result.get("text", "").strip()
        if suggestion:
            return suggestion
        return suggestion_fallback(generator, locale)
    except Exception as exc:
        logger.warning(
            "Failed to generate LLM suggestion: %s, falling back to i18n template",
            exc,
        )
        return suggestion_fallback(generator, locale)
