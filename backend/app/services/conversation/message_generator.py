"""Message generator facade for user-facing conversation responses."""

import logging
from typing import Any, Callable, Dict, Optional

from backend.app.models.playbook import HandoffPlan
from backend.app.services.conversation.message_generator_core import (
    format_workflow_summary,
    generate_confirmation_message as generate_confirmation_message_helper,
    generate_readonly_feedback as generate_readonly_feedback_helper,
    generate_single_step_response,
    generate_suggestion_message as generate_suggestion_message_helper,
    generate_workflow_response as generate_workflow_response_helper,
    generate_workflow_summary as generate_workflow_summary_helper,
    get_cancel_button_label,
    get_confirm_button_label,
)
from backend.app.services.intent_analyzer import IntentAnalysisResult

logger = logging.getLogger(__name__)


class MessageGenerator:
    """Generate natural language messages using an optional LLM provider."""

    def __init__(
        self,
        llm_provider=None,
        default_locale: str = "en",
        llm_provider_factory: Optional[Callable[[], Any]] = None,
    ):
        self.llm_provider = llm_provider
        self.default_locale = default_locale
        self.llm_provider_factory = llm_provider_factory

    def _ensure_llm_provider(self):
        """Build the provider lazily so Gemini-only paths do not touch Vertex eagerly."""
        if self.llm_provider is None and self.llm_provider_factory:
            try:
                self.llm_provider = self.llm_provider_factory()
            except Exception as exc:
                logger.warning(
                    "Failed to lazily initialize llm_provider: %s",
                    exc,
                    exc_info=True,
                )
        return self.llm_provider

    async def generate_readonly_feedback(
        self,
        timeline_item: Dict[str, Any],
        task_result: Optional[Dict[str, Any]] = None,
        locale: Optional[str] = None,
    ) -> str:
        """Generate natural feedback message for readonly task completion."""
        return await generate_readonly_feedback_helper(
            generator=self,
            timeline_item=timeline_item,
            task_result=task_result,
            locale=locale,
        )

    async def generate_suggestion_message(
        self,
        pack_id: str,
        task_result: Dict[str, Any],
        timeline_item: Dict[str, Any],
        locale: Optional[str] = None,
    ) -> str:
        """Generate natural suggestion message for soft-write tasks."""
        return await generate_suggestion_message_helper(
            generator=self,
            pack_id=pack_id,
            task_result=task_result,
            timeline_item=timeline_item,
            locale=locale,
        )

    async def generate_confirmation_message(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        timeline_item: Optional[Dict[str, Any]] = None,
        locale: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate detailed confirmation message for external-write actions."""
        return await generate_confirmation_message_helper(
            generator=self,
            action_type=action_type,
            action_params=action_params,
            timeline_item=timeline_item,
            locale=locale,
        )

    def _get_confirm_button_label(
        self,
        action_type: str,
        locale: Optional[str] = None,
    ) -> str:
        """Get confirm button label based on action type."""
        return get_confirm_button_label(
            generator=self,
            action_type=action_type,
            locale=locale,
        )

    def _get_cancel_button_label(self, locale: Optional[str] = None) -> str:
        """Get cancel button label."""
        return get_cancel_button_label(generator=self, locale=locale)

    async def generate_workflow_response(
        self,
        user_input: str,
        intent_result: IntentAnalysisResult,
        context: Optional[Dict[str, Any]] = None,
        locale: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate LLM response that may include a handoff plan."""
        return await generate_workflow_response_helper(
            generator=self,
            user_input=user_input,
            intent_result=intent_result,
            context=context,
            locale=locale,
        )

    async def _generate_single_step_response(
        self,
        user_input: str,
        intent_result: IntentAnalysisResult,
        context: Optional[Dict[str, Any]],
        locale: Optional[str],
    ) -> str:
        """Generate response for single-step requests."""
        return await generate_single_step_response(
            user_input=user_input,
            intent_result=intent_result,
            context=context,
            locale=locale,
        )

    def _format_workflow_summary(self, handoff_plan: HandoffPlan) -> str:
        """Format workflow steps as a readable summary."""
        return format_workflow_summary(handoff_plan=handoff_plan)

    async def generate_workflow_summary(
        self,
        workflow_result: Dict[str, Any],
        handoff_plan: HandoffPlan,
        locale: Optional[str] = None,
    ) -> str:
        """Generate user-friendly summary of workflow execution results."""
        return await generate_workflow_summary_helper(
            generator=self,
            workflow_result=workflow_result,
            handoff_plan=handoff_plan,
            locale=locale,
        )
