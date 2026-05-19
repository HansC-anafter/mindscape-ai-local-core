"""Readonly feedback generation helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.capabilities.core_llm.services.generate import run as llm_generate
from backend.app.services.i18n_service import I18nService

logger = logging.getLogger(__name__)


def readonly_fallback(generator: Any, timeline_item: Dict[str, Any], locale: Optional[str]) -> str:
    summary = timeline_item.get("summary", "")
    i18n = I18nService(default_locale=locale or generator.default_locale)
    return i18n.t(
        "conversation_orchestrator",
        "feedback.readonly",
        summary=summary or "Analysis completed",
    )


async def generate_readonly_feedback(
    *,
    generator: Any,
    timeline_item: Dict[str, Any],
    task_result: Optional[Dict[str, Any]] = None,
    locale: Optional[str] = None,
) -> str:
    """Generate natural feedback for readonly task completion."""
    try:
        provider = generator._ensure_llm_provider()
        if not provider:
            return readonly_fallback(generator, timeline_item, locale)

        title = timeline_item.get("title", "")
        summary = timeline_item.get("summary", "")
        context_parts = []
        if title:
            context_parts.append(f"Title: {title}")
        if summary:
            context_parts.append(f"Summary: {summary}")
        if task_result:
            result_summary = task_result.get("message") or task_result.get("summary", "")
            if result_summary:
                context_parts.append(f"Result: {result_summary}")

        context = "\n".join(context_parts) if context_parts else "Analysis completed"
        system_prompt = """You are a helpful AI assistant providing feedback to users about completed analysis tasks.

Generate a brief, natural, and friendly feedback message that:
1. Acknowledges what was analyzed
2. Highlights key findings or results
3. Is concise (1-2 sentences)
4. Uses natural, conversational language

Do not use generic greetings or formal phrases. Be direct and helpful."""
        user_prompt = f"""The following analysis task has been completed:

{context}

Generate a natural feedback message for the user describing what was analyzed and the key findings."""

        result = await llm_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.7,
            llm_provider=provider,
            target_language=locale or generator.default_locale,
        )
        feedback = result.get("text", "").strip()
        if feedback:
            return feedback
        return readonly_fallback(generator, timeline_item, locale)
    except Exception as exc:
        logger.warning(
            "Failed to generate LLM feedback: %s, falling back to i18n template",
            exc,
        )
        return readonly_fallback(generator, timeline_item, locale)
