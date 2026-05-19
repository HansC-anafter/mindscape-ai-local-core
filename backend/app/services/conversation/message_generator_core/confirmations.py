"""External-write confirmation generation helpers."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.capabilities.core_llm.services.generate import run as llm_generate
from backend.app.services.i18n_service import I18nService

logger = logging.getLogger(__name__)


def get_confirm_button_label(
    *,
    generator: Any,
    action_type: str,
    locale: Optional[str] = None,
) -> str:
    """Get confirm button label based on action type."""
    i18n = I18nService(default_locale=locale or generator.default_locale)
    if "wordpress" in action_type.lower() or "publish" in action_type.lower():
        return i18n.t(
            "conversation_orchestrator",
            "confirmation.button_publish",
            fallback="Publish",
        )
    if "export" in action_type.lower():
        return i18n.t(
            "conversation_orchestrator",
            "confirmation.button_export",
            fallback="Export",
        )
    return i18n.t(
        "conversation_orchestrator",
        "confirmation.button_confirm",
        fallback="Confirm",
    )


def get_cancel_button_label(*, generator: Any, locale: Optional[str] = None) -> str:
    """Get cancel button label."""
    i18n = I18nService(default_locale=locale or generator.default_locale)
    return i18n.t(
        "conversation_orchestrator",
        "confirmation.button_cancel",
        fallback="Cancel",
    )


def confirmation_fallback(
    *,
    generator: Any,
    action_type: str,
    locale: Optional[str],
) -> Dict[str, Any]:
    i18n = I18nService(default_locale=locale or generator.default_locale)
    return {
        "message": i18n.t(
            "conversation_orchestrator",
            "confirmation.external_write",
            action_type=action_type,
        ),
        "confirm_buttons": [
            {
                "label": i18n.t(
                    "conversation_orchestrator",
                    "confirmation.button_confirm",
                ),
                "action": action_type,
                "confirm": True,
            },
            {
                "label": i18n.t(
                    "conversation_orchestrator",
                    "confirmation.button_cancel",
                ),
                "action": "cancel",
            },
        ],
    }


async def generate_confirmation_message(
    *,
    generator: Any,
    action_type: str,
    action_params: Dict[str, Any],
    timeline_item: Optional[Dict[str, Any]] = None,
    locale: Optional[str] = None,
) -> Dict[str, Any]:
    """Generate detailed confirmation message for external-write actions."""
    try:
        provider = generator._ensure_llm_provider()
        if not provider:
            return confirmation_fallback(
                generator=generator,
                action_type=action_type,
                locale=locale,
            )

        context_parts = [f"Action: {action_type}"]
        if timeline_item:
            title = timeline_item.get("title", "")
            summary = timeline_item.get("summary", "")
            if title:
                context_parts.append(f"Content title: {title}")
            if summary:
                context_parts.append(f"Content summary: {summary}")
        if action_params:
            if "title" in action_params:
                context_parts.append(f"Title: {action_params['title']}")
            if "url" in action_params:
                context_parts.append(f"Target URL: {action_params['url']}")

        context = "\n".join(context_parts)
        system_prompt = """You are a helpful AI assistant asking for user confirmation before performing external actions.

Generate a clear, detailed confirmation message that:
1. Explains what action will be performed
2. Mentions key details (title, target, etc.)
3. Asks for explicit confirmation
4. Is professional and clear
5. Is concise but informative (2-3 sentences)

Do not use generic greetings. Be direct and clear about the action."""
        user_prompt = f"""The following external action is about to be performed:

{context}

Generate a detailed confirmation message asking the user to confirm this action."""

        result = await llm_generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.5,
            llm_provider=provider,
            target_language=locale or generator.default_locale,
        )
        confirmation_message = result.get("text", "").strip()
        if not confirmation_message:
            fallback = confirmation_fallback(
                generator=generator,
                action_type=action_type,
                locale=locale,
            )
            confirmation_message = fallback["message"]

        return {
            "message": confirmation_message,
            "confirm_buttons": [
                {
                    "label": generator._get_confirm_button_label(action_type, locale),
                    "action": action_type,
                    "confirm": True,
                },
                {
                    "label": generator._get_cancel_button_label(locale),
                    "action": "cancel",
                },
            ],
        }
    except Exception as exc:
        logger.warning(
            "Failed to generate LLM confirmation: %s, falling back to i18n template",
            exc,
        )
        return confirmation_fallback(
            generator=generator,
            action_type=action_type,
            locale=locale,
        )
