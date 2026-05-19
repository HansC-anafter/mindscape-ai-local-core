"""Confirmation message generation for external-write CTA actions."""

from typing import Any, Dict, Optional

from backend.app.shared.llm_provider_helper import (
    create_llm_provider_manager,
    get_llm_provider_from_settings,
)


class CTAConfirmationMixin:
    """Generate confirmation prompts for external write actions."""

    async def _generate_confirmation(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        timeline_item: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Generate confirmation message for external_write action.

        Args:
            action_type: Action type.
            action_params: Action parameters.
            timeline_item: Timeline item with action content.

        Returns:
            Dict with confirmation message and buttons.
        """
        from backend.app.services.message_generator import MessageGenerator

        llm_manager = create_llm_provider_manager()
        llm_provider = get_llm_provider_from_settings(llm_manager)

        message_generator = MessageGenerator(
            llm_provider=llm_provider,
            default_locale=self.i18n.default_locale,
        )

        return await message_generator.generate_confirmation_message(
            action_type=action_type,
            action_params=action_params,
            timeline_item=timeline_item,
            locale=self.i18n.default_locale,
        )
