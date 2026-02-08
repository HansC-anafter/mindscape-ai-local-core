"""
Playbook Selector

Layer 3: Playbook selection and context preparation based on task domain and user input.
"""

import re
import logging
from typing import Dict, List, Optional, Any

from backend.app.models.mindscape import MindscapeProfile, IntentCard
from backend.app.models.playbook import (
    HandoffPlan,
    WorkflowStep,
    PlaybookKind,
    InteractionMode,
)
from backend.app.shared.llm_utils import call_llm, build_prompt

from .models import TaskDomain
from .utils import parse_json_from_response

logger = logging.getLogger(__name__)


class PlaybookSelector:
    """Layer 3: Playbook selection and context preparation"""

    def __init__(self, playbook_service=None, llm_provider=None):
        """
        Initialize PlaybookSelector

        Args:
            playbook_service: PlaybookService instance (required, for unified query)
            llm_provider: LLM provider instance (optional, for LLM-based playbook matching)
        """
        if not playbook_service:
            raise ValueError(
                "PlaybookService is required. PlaybookLoader has been removed."
            )
        self.playbook_service = playbook_service
        self.llm_provider = llm_provider
        self.use_new_interface = True

    async def select_playbook(
        self,
        task_domain: TaskDomain,
        user_input: str,
        profile: Optional[MindscapeProfile] = None,
        locale: Optional[str] = None,
        workspace_id: Optional[str] = None,
    ) -> tuple[Optional[str], float, Optional[HandoffPlan]]:
        """
        Select appropriate playbook based on task domain and user input using dynamic playbook discovery

        Args:
            task_domain: Task domain
            user_input: User input text
            profile: User profile (optional)
            locale: Language locale (optional)
            workspace_id: Workspace ID (optional, for PlaybookService priority)

        Returns:
            (playbook_code, confidence, handoff_plan)
            - playbook_code: Selected playbook code
            - confidence: Selection confidence (0.0-1.0)
            - handoff_plan: HandoffPlan if playbook.json exists, None otherwise
        """
        # Dynamically load all available playbooks
        available_playbooks = await self.playbook_service.list_playbooks(
            workspace_id=workspace_id, locale=locale or "zh-TW"
        )

        if not available_playbooks:
            logger.warning("No playbooks available for selection")
            return None, 0.0, None

        # Use LLM to match user input and task domain to the best playbook
        playbook_code = await self._match_playbook_by_llm(
            available_playbooks=available_playbooks,
            task_domain=task_domain,
            user_input=user_input,
        )

        if playbook_code:
            # Load the selected playbook
            playbook_run = await self.playbook_service.load_playbook_run(
                playbook_code=playbook_code,
                locale=locale or "zh-TW",
                workspace_id=workspace_id,
            )

            if not playbook_run:
                logger.warning(f"Playbook {playbook_code} not found after selection")
                return None, 0.0, None

            if playbook_run.has_json():
                handoff_plan = self._generate_handoff_plan(
                    playbook_run=playbook_run, user_input=user_input, profile=profile
                )
                return playbook_code, 0.8, handoff_plan
            else:
                # Playbook exists but no playbook.json - return playbook_code without handoff_plan
                logger.info(
                    f"Playbook {playbook_code} found but does not have playbook.json. Only playbook.md found. Returning playbook_code without handoff_plan."
                )
                return playbook_code, 0.8, None

        return None, 0.0, None

    async def _match_playbook_by_llm(
        self, available_playbooks: List[Any], task_domain: TaskDomain, user_input: str
    ) -> Optional[str]:
        """
        Use LLM to match the best playbook from available playbooks based on task domain and user input

        Args:
            available_playbooks: List of available playbook metadata
            task_domain: Task domain
            user_input: User input text

        Returns:
            Selected playbook code or None
        """
        if not available_playbooks:
            return None

        # Build playbook list for LLM
        playbook_list = []
        for pb in available_playbooks:
            playbook_info = f"- {pb.playbook_code}: {pb.name}"
            if pb.description:
                playbook_info += f" ({pb.description[:300]})"
            if pb.tags:
                playbook_info += f" [tags: {', '.join(pb.tags)}]"
            playbook_list.append(playbook_info)

        playbooks_text = "\n".join(playbook_list)

        # Playbook selection should be based on user_input, not limited by hardcoded task_domain
        # task_domain is only used as a hint, not a requirement
        task_domain_hint = (
            f" (Task domain hint: {task_domain.value})"
            if task_domain != TaskDomain.UNKNOWN
            else ""
        )
        prompt = f"""Given the user request, select the most appropriate playbook from the available list.

User request: "{user_input}"{task_domain_hint}

Available playbooks:
{playbooks_text}

Return the playbook_code of the best matching playbook in JSON format:
{{
    "playbook_code": "playbook_code_here",
    "confidence": 0.0-1.0,
    "reason": "brief explanation"
}}

If no playbook matches well, return {{"playbook_code": null, "confidence": 0.0, "reason": "..."}}
"""

        if not self.llm_provider:
            logger.warning(
                "LLM provider not available, cannot use LLM for playbook matching"
            )
            return None

        try:
            # Build messages using build_prompt
            messages = build_prompt(
                system_prompt="You are a playbook selection assistant. Analyze user requests and select the most appropriate playbook from the available list.",
                user_prompt=prompt,
            )

            # Get model name from system settings, or use None to let llm_provider use its default
            from backend.app.shared.llm_provider_helper import (
                get_model_name_from_chat_model,
            )

            model_name = None
            try:
                model_name = get_model_name_from_chat_model()
            except Exception as e:
                logger.debug(
                    f"Failed to get model name from chat_model: {e}, using llm_provider default"
                )

            # Use unified call_llm tool with existing llm_provider
            # If model_name is None, call_llm will use llm_provider's default model
            response_dict = await call_llm(
                messages=messages, llm_provider=self.llm_provider, model=model_name
            )

            response_text = response_dict.get("text", "")
            if not response_text:
                logger.warning("LLM returned empty response")
                return None

            logger.info(f"LLM response text: {response_text[:200]}...")

            result = parse_json_from_response(response_text)
            if not result:
                return None

            selected_code = result.get("playbook_code")

            if selected_code:
                # Verify the playbook exists in the list
                playbook_codes = [pb.playbook_code for pb in available_playbooks]
                if selected_code in playbook_codes:
                    logger.info(
                        f"LLM selected playbook: {selected_code} (confidence: {result.get('confidence', 0.0)})"
                    )
                    return selected_code
                else:
                    logger.warning(
                        f"LLM selected playbook {selected_code} not in available list"
                    )

            return None

        except Exception as e:
            logger.warning(f"LLM playbook matching failed: {e}")
            return None

    def _generate_handoff_plan(
        self,
        playbook_run: Any,
        user_input: str,
        profile: Optional[MindscapeProfile] = None,
    ) -> HandoffPlan:
        """
        Generate HandoffPlan from playbook.run

        Args:
            playbook_run: PlaybookRun object (contains both .md and .json)
            user_input: User input text
            profile: User profile (optional)

        Returns:
            HandoffPlan with workflow steps based on playbook.json
        """
        from backend.app.models.playbook import PlaybookRun

        if not playbook_run or not playbook_run.playbook_json:
            raise ValueError(
                "playbook_run must have playbook_json to generate HandoffPlan"
            )

        interaction_modes = playbook_run.playbook.metadata.interaction_mode or [
            InteractionMode.CONVERSATIONAL
        ]

        workflow_step = WorkflowStep(
            playbook_code=playbook_run.playbook.metadata.playbook_code,
            kind=PlaybookKind(playbook_run.playbook_json.kind),
            inputs={},
            interaction_mode=[InteractionMode(mode) for mode in interaction_modes],
        )

        handoff_plan = HandoffPlan(steps=[workflow_step], context={})

        return handoff_plan

    def prepare_playbook_context(
        self,
        playbook_code: str,
        user_input: str,
        profile: Optional[MindscapeProfile] = None,
        active_intents: Optional[List[IntentCard]] = None,
    ) -> Dict[str, Any]:
        """
        Prepare initial context for playbook execution

        Returns:
            Context dictionary with project_id, locale, message, etc.
        """
        context = {
            "locale": None,
            "project_id": None,
            "message": user_input,  # Pass user's original message to playbook
        }

        # Determine locale from profile
        if profile and profile.preferences:
            context["locale"] = (
                profile.preferences.preferred_content_language or "zh-TW"
            )

        # Try to extract project_id from active intents
        if active_intents:
            # Look for intent with matching tags/category
            for intent in active_intents:
                if intent.metadata and "project_id" in intent.metadata:
                    context["project_id"] = intent.metadata["project_id"]
                    break

        # Extract project hints from user input
        project_match = re.search(
            r"(?:專案|project)[：:]\s*(\w+)", user_input, re.IGNORECASE
        )
        if project_match:
            # This is a hint, actual project_id should come from database lookup
            pass

        return context
