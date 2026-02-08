"""
LLM-Based Intent Matcher

Provides semantic understanding for intent classification using LLM.
"""

import logging
from typing import Dict, List, Optional, Any

from backend.app.models.mindscape import IntentCard
from backend.app.shared.llm_utils import call_llm, build_prompt

from .models import InteractionType, TaskDomain
from .utils import parse_json_from_response

logger = logging.getLogger(__name__)


class LLMBasedIntentMatcher:
    """LLM-based matching for semantic understanding"""

    def __init__(self, llm_provider=None):
        # Validate llm_provider is a provider object, not a string
        if llm_provider is not None:
            if isinstance(llm_provider, str):
                logger.warning(
                    f"LLMBasedIntentMatcher received string instead of provider object: {llm_provider[:50]}..."
                )
                self.llm_provider = None
            elif not hasattr(llm_provider, "chat_completion"):
                logger.warning(
                    f"LLMBasedIntentMatcher received invalid provider type: {type(llm_provider)}"
                )
                self.llm_provider = None
            else:
                self.llm_provider = llm_provider
        else:
            self.llm_provider = None

    async def determine_interaction_type(
        self, user_input: str, channel: str = "api", model_name: Optional[str] = None
    ) -> tuple[InteractionType, float]:
        """
        Use LLM to determine interaction type (Layer 1)

        Returns:
            (InteractionType, confidence)
        """
        if not self.llm_provider:
            return InteractionType.UNKNOWN, 0.0

        # Double-check provider has required method
        if not hasattr(self.llm_provider, "chat_completion"):
            logger.error(
                f"llm_provider does not have chat_completion method: {type(self.llm_provider)}"
            )
            return InteractionType.UNKNOWN, 0.0

        prompt = f"""Analyze the following user input to determine the interaction type:

User input: "{user_input}"
Channel: {channel}

Please determine if this is:
1. Q&A - Pure Q&A, no playbook needed
2. START_PLAYBOOK - User wants to start/continue a playbook
3. MANAGE_SETTINGS - User wants to manage settings (language, habit frequency, etc.)

Return in JSON format:
{{
    "interaction_type": "qa|start_playbook|manage_settings",
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}
"""

        try:
            # Get model name from system settings
            from backend.app.services.system_settings_store import SystemSettingsStore
            from backend.app.shared.llm_provider_helper import (
                get_model_name_from_chat_model,
            )

            try:
                # Use provided model, or system setting, or fallback
                model_name = (
                    model_name or get_model_name_from_chat_model() or "gpt-4o-mini"
                )
            except:
                model_name = model_name or "gpt-4o-mini"

            # Build messages using build_prompt
            messages = build_prompt(
                system_prompt="You are an intent analysis assistant. Analyze user input to determine interaction type.",
                user_prompt=prompt,
            )

            response_dict = await call_llm(
                messages=messages, llm_provider=self.llm_provider, model=model_name
            )

            response_text = response_dict.get("text", "")
            if not response_text:
                logger.warning(
                    "LLM returned empty response for interaction type determination"
                )
                return InteractionType.UNKNOWN, 0.0

            # Parse JSON response
            result = parse_json_from_response(response_text)
            if not result:
                return InteractionType.UNKNOWN, 0.0

            interaction_type_str = result.get("interaction_type", "unknown")
            confidence = float(result.get("confidence", 0.0))

            try:
                interaction_type = InteractionType(interaction_type_str)
            except ValueError:
                interaction_type = InteractionType.UNKNOWN

            return interaction_type, confidence

        except Exception as e:
            logger.warning(f"LLM interaction type determination failed: {e}")
            return InteractionType.UNKNOWN, 0.0

    async def determine_task_domain(
        self,
        user_input: str,
        active_intents: Optional[List[IntentCard]] = None,
        model_name: Optional[str] = None,
    ) -> tuple[TaskDomain, float]:
        """
        Use LLM to determine task domain (Layer 2)

        Args:
            user_input: User input
            active_intents: Active intent cards for few-shot examples
            model_name: Optional model name override

        Returns:
            (TaskDomain, confidence)
        """
        if not self.llm_provider:
            return TaskDomain.UNKNOWN, 0.0

        # Build few-shot examples from active intents
        few_shot_examples = ""
        if active_intents:
            examples = []
            for intent in active_intents[:3]:
                # Map intent category/tags to task domain
                domain_hint = self._map_intent_to_domain(intent)
                examples.append(f'- "{intent.title}": {domain_hint}')
            if examples:
                few_shot_examples = "\nReference examples:\n" + "\n".join(examples)

        prompt = f"""Analyze the following user input to determine the task domain:

User input: "{user_input}"
{few_shot_examples}

Please determine which task domain this belongs to:
1. PROPOSAL_WRITING - Writing proposals, grant applications
2. YEARLY_REVIEW - Annual review, yearly book compilation
3. HABIT_LEARNING - Habit organization, habit learning
4. PROJECT_PLANNING - Project planning, task breakdown
5. CONTENT_WRITING - Content writing, copywriting
6. UNKNOWN - Cannot determine

Return in JSON format:
{{
    "task_domain": "proposal_writing|yearly_review|habit_learning|project_planning|content_writing|unknown",
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}
"""

        try:
            # Get model name from system settings
            from backend.app.shared.llm_provider_helper import (
                get_model_name_from_chat_model,
            )

            try:
                # Use provided model, or system setting, or fallback
                model_name = (
                    model_name or get_model_name_from_chat_model() or "gpt-4o-mini"
                )
            except:
                model_name = model_name or "gpt-4o-mini"

            # Build messages using build_prompt
            messages = build_prompt(
                system_prompt="You are a task domain analysis assistant. Analyze user input to determine task domain.",
                user_prompt=prompt,
            )

            response_dict = await call_llm(
                messages=messages, llm_provider=self.llm_provider, model=model_name
            )

            response_text = response_dict.get("text", "")
            if not response_text:
                logger.warning(
                    "LLM returned empty response for task domain determination"
                )
                return TaskDomain.UNKNOWN, 0.0

            result = parse_json_from_response(response_text)
            if not result:
                return TaskDomain.UNKNOWN, 0.0

            domain_str = result.get("task_domain", "unknown")
            confidence = float(result.get("confidence", 0.0))

            try:
                task_domain = TaskDomain(domain_str)
            except ValueError:
                task_domain = TaskDomain.UNKNOWN

            return task_domain, confidence

        except Exception as e:
            logger.warning(f"LLM task domain determination failed: {e}")
            return TaskDomain.UNKNOWN, 0.0

    def _map_intent_to_domain(self, intent: IntentCard) -> str:
        """Map intent card to task domain hint"""
        title_lower = intent.title.lower()
        tags_lower = [tag.lower() for tag in intent.tags]

        if any(
            kw in title_lower
            for kw in ["補助", "申請", "proposal", "申請書", "grant", "application"]
        ):
            return "PROPOSAL_WRITING"
        elif any(
            kw in title_lower
            for kw in ["年度", "年終", "yearly", "回顧", "review", "annual"]
        ):
            return "YEARLY_REVIEW"
        elif any(kw in title_lower for kw in ["習慣", "habit"]):
            return "HABIT_LEARNING"
        elif any(kw in title_lower for kw in ["專案", "project", "規劃", "planning"]):
            return "PROJECT_PLANNING"
        else:
            return "CONTENT_WRITING"
