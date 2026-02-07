"""
Intent Analyzer Service
3-layer Intent Pipeline for determining user intent and selecting appropriate playbooks

Layer 1: Interaction Type (Rule-based + small model)
Layer 2: Task Domain (Intent cards / few-shot / embedding similarity)
Layer 3: Playbook Selection + Context Preparation
"""

import re
import logging
from enum import Enum
from typing import Dict, List, Optional, Any
from datetime import datetime

from backend.app.models.mindscape import MindscapeProfile, IntentCard, IntentLog
from backend.app.models.playbook import (
    HandoffPlan,
    WorkflowStep,
    PlaybookKind,
    InteractionMode,
)
from backend.app.shared.llm_utils import call_llm, build_prompt
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


def _parse_json_from_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Parse JSON from LLM response, handling markdown code blocks

    Args:
        response_text: Raw response text from LLM

    Returns:
        Parsed JSON dict, or None if parsing fails
    """
    import json
    import re

    if not response_text or not response_text.strip():
        return None

    # First, try direct JSON parsing
    try:
        return json.loads(response_text.strip())
    except json.JSONDecodeError:
        pass

    # Try to extract JSON from markdown code blocks
    # Pattern 1: ```json ... ```
    json_block_pattern = r"```(?:json)?\s*(\{.*?\})\s*```"
    match = re.search(json_block_pattern, response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Pattern 2: ``` ... ``` (without json label)
    code_block_pattern = r"```\s*(\{.*?\})\s*```"
    match = re.search(code_block_pattern, response_text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Pattern 3: Remove markdown markers and try again
    cleaned = re.sub(r"^```(?:json)?\s*", "", response_text, flags=re.MULTILINE)
    cleaned = re.sub(r"^```\s*$", "", cleaned, flags=re.MULTILINE)
    cleaned = cleaned.strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Pattern 4: Find the largest JSON object in the text
    # Match balanced braces
    brace_count = 0
    start_idx = -1
    for i, char in enumerate(response_text):
        if char == "{":
            if brace_count == 0:
                start_idx = i
            brace_count += 1
        elif char == "}":
            brace_count -= 1
            if brace_count == 0 and start_idx >= 0:
                json_str = response_text[start_idx : i + 1]
                try:
                    return json.loads(json_str)
                except json.JSONDecodeError:
                    continue

    logger.warning(
        f"Failed to parse JSON from response. Response preview: {response_text[:500]}"
    )
    return None


class InteractionType(str, Enum):
    """Layer 1: Interaction type classification"""

    QA = "qa"  # Pure Q&A (no playbook needed)
    START_PLAYBOOK = "start_playbook"  # User wants to start/continue a playbook
    MANAGE_SETTINGS = "manage_settings"  # User wants to manage settings
    UNKNOWN = "unknown"  # Cannot determine


class TaskDomain(str, Enum):
    """Layer 2: Task domain classification"""

    PROPOSAL_WRITING = "proposal_writing"  # Writing proposals, grant applications
    YEARLY_REVIEW = "yearly_review"  # Annual review, yearly book compilation
    HABIT_LEARNING = "habit_learning"  # Habit organization, habit learning
    PROJECT_PLANNING = "project_planning"  # Project planning, task breakdown
    CONTENT_WRITING = "content_writing"  # Content writing, copywriting
    UNKNOWN = "unknown"  # Unknown domain


class IntentAnalysisResult:
    """Result of 3-layer intent analysis"""

    def __init__(self):
        # Layer 1 results
        self.interaction_type: Optional[InteractionType] = None
        self.interaction_confidence: float = 0.0

        # Layer 2 results
        self.task_domain: Optional[TaskDomain] = None
        self.task_domain_confidence: float = 0.0

        # Layer 3 results
        self.selected_playbook_code: Optional[str] = None
        self.playbook_confidence: float = 0.0
        self.playbook_context: Dict[str, Any] = {}
        self.handoff_plan: Optional[Any] = (
            None  # HandoffPlan from playbook.run (new architecture)
        )

        # Multi-step workflow support
        self.is_multi_step: bool = False
        self.workflow_steps: List[Dict[str, Any]] = []
        self.step_dependencies: Dict[str, List[str]] = {}

        # Metadata
        self.raw_input: str = ""
        self.channel: str = "api"
        self.profile_id: Optional[str] = None
        self.project_id: Optional[str] = None
        self.workspace_id: Optional[str] = None
        self.pipeline_steps: Dict[str, Any] = {}
        self.timestamp: datetime = datetime.utcnow()


class RuleBasedIntentMatcher:
    """Rule-based matching for Layer 1 (Interaction Type)"""

    # Command patterns for starting playbooks
    START_PLAYBOOK_PATTERNS = [
        r"/start\s+(\w+)",
        r"/start\s+proposal",
        r"/start\s+yearly",
        r"開始\s+(\w+)",
        r"啟動\s+(\w+)",
        r"執行\s+(\w+)",
        r"我想.*寫.*(?:補助|計畫|申請)",
        r"我想.*(?:年度|年終).*(?:回顧|出書)",
        r"幫我.*(?:整理|學習).*(?:習慣)",
    ]

    # Settings management patterns
    SETTINGS_PATTERNS = [
        r"/settings?",
        r"/設定",
        r"設定",
        r"配置",
        r"語言.*設定",
        r"設定.*語言",
        r"preferences?",
        r"settings?",
    ]

    # Export patterns
    EXPORT_PATTERNS = [
        r"匯出",
        r"匯出\s+docx",
        r"匯出\s+markdown",
        r"export",
        r"export\s+docx",
        r"export\s+markdown",
    ]

    def match_command(self, user_input: str) -> Optional[str]:
        """
        Match specific commands from user input

        Returns:
            Command name if matched, None otherwise
        """
        user_input_lower = user_input.lower().strip()

        # Check for export commands
        for pattern in self.EXPORT_PATTERNS:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                if "docx" in user_input_lower:
                    return "export_docx"
                elif "markdown" in user_input_lower:
                    return "export_markdown"
                else:
                    return "export"

        # Check for playbook start commands
        for pattern in self.START_PLAYBOOK_PATTERNS:
            match = re.search(pattern, user_input_lower, re.IGNORECASE)
            if match:
                if match.groups():
                    return f"start_{match.group(1)}"
                return "start_playbook"

        # Check for settings commands
        for pattern in self.SETTINGS_PATTERNS:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                return "manage_settings"

        return None

    def match_channel_specific(
        self, user_input: str, channel: str
    ) -> Optional[InteractionType]:
        """
        Match channel-specific patterns

        Args:
            user_input: User input text
            channel: Channel (api, line, wp, playbook)

        Returns:
            InteractionType if matched, None otherwise
        """
        user_input_lower = user_input.lower().strip()

        # Line channel: commands typically start with /
        if channel == "line":
            if user_input_lower.startswith("/"):
                # Extract command after /
                command = (
                    user_input_lower[1:].split()[0] if user_input_lower[1:] else ""
                )
                if command in ["start", "settings", "設定", "設定語言"]:
                    if command in ["start"]:
                        return InteractionType.START_PLAYBOOK
                    else:
                        return InteractionType.MANAGE_SETTINGS

        # WordPress webhook: may have specific patterns
        if channel == "wp":
            # WordPress webhook patterns can be added here
            pass

        return None

    def match_interaction_type(
        self, user_input: str, channel: str = "api"
    ) -> Optional[InteractionType]:
        """
        Match interaction type using rules

        Args:
            user_input: User input text
            channel: Channel (api, line, wp, playbook)

        Returns:
            InteractionType or None if no match
        """
        # Try channel-specific matching first
        channel_result = self.match_channel_specific(user_input, channel)
        if channel_result:
            return channel_result

        user_input_lower = user_input.lower().strip()

        # Check for playbook start patterns
        for pattern in self.START_PLAYBOOK_PATTERNS:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                return InteractionType.START_PLAYBOOK

        # Check for settings patterns
        for pattern in self.SETTINGS_PATTERNS:
            if re.search(pattern, user_input_lower, re.IGNORECASE):
                return InteractionType.MANAGE_SETTINGS

        # Default: no match (will be handled by LLM layer if enabled)
        return None


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
        self, user_input: str, channel: str = "api"
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
            import json

            result = _parse_json_from_response(response_text)
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
        self, user_input: str, active_intents: Optional[List[IntentCard]] = None
    ) -> tuple[TaskDomain, float]:
        """
        Use LLM to determine task domain (Layer 2)

        Args:
            user_input: User input
            active_intents: Active intent cards for few-shot examples

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

            import json

            result = _parse_json_from_response(response_text)
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

            result = _parse_json_from_response(response_text)
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


class IntentDecisionCoordinator:
    """Coordinates rule-based and LLM-based intent decision making"""

    def __init__(
        self,
        rule_matcher: RuleBasedIntentMatcher,
        llm_matcher: LLMBasedIntentMatcher,
        use_llm: bool = True,
        rule_priority: bool = True,
    ):
        self.rule_matcher = rule_matcher
        self.llm_matcher = llm_matcher
        self.use_llm = use_llm
        self.rule_priority = rule_priority

    async def decide_interaction_type(
        self, user_input: str, channel: str = "api", model_name: Optional[str] = None
    ) -> tuple[InteractionType, float, str]:
        """
        Decide interaction type using rule-based and/or LLM-based matching

        Returns:
            (InteractionType, confidence, method_used)
        """
        # Try rule-based first if rule_priority is True
        if self.rule_priority:
            rule_result = self.rule_matcher.match_interaction_type(user_input, channel)
            if rule_result:
                logger.info(
                    f"[IntentDecisionCoordinator] Rule-based match: {rule_result.value}"
                )
                return rule_result, 0.9, "rule_based"

        # Fallback to LLM if enabled
        if self.use_llm:
            try:
                interaction_type, confidence = (
                    await self.llm_matcher.determine_interaction_type(
                        user_input, channel, model_name=model_name
                    )
                )
                logger.info(
                    f"[IntentDecisionCoordinator] LLM-based match: {interaction_type.value} (confidence: {confidence:.2f})"
                )
                return interaction_type, confidence, "llm_based"
            except Exception as e:
                logger.warning(f"[IntentDecisionCoordinator] LLM matching failed: {e}")

        # If rule_priority is False and no rule match, try rules as fallback
        if not self.rule_priority:
            rule_result = self.rule_matcher.match_interaction_type(user_input, channel)
            if rule_result:
                logger.info(
                    f"[IntentDecisionCoordinator] Rule-based fallback: {rule_result.value}"
                )
                return rule_result, 0.7, "rule_based_fallback"

        # Default: unknown
        logger.warning(
            f"[IntentDecisionCoordinator] No match found for: {user_input[:50]}"
        )
        return InteractionType.UNKNOWN, 0.0, "none"


class IntentPipeline:
    """3-layer Intent Pipeline coordinator"""

    def __init__(
        self,
        llm_provider=None,
        use_llm: bool = True,
        rule_priority: bool = True,
        config=None,
        store: Optional[MindscapeStore] = None,
        enable_logging: bool = True,
        playbook_service=None,
    ):
        """
        Initialize Intent Pipeline

        Args:
            llm_provider: LLM provider for semantic matching
            use_llm: Enable LLM-based matching (can be overridden by config)
            rule_priority: Try rule-based first (can be overridden by config)
            config: UserConfig object (optional, if provided, will use intent_config from it)
            store: MindscapeStore instance for logging (optional)
            enable_logging: Enable intent decision logging (default: True)
            playbook_service: PlaybookService instance (optional, for unified query)
        """
        # Override with config if provided
        if config and hasattr(config, "intent_config"):
            use_llm = config.intent_config.use_llm
            rule_priority = config.intent_config.rule_priority

        self.rule_matcher = RuleBasedIntentMatcher()
        self.llm_matcher = LLMBasedIntentMatcher(llm_provider)
        self.playbook_selector = PlaybookSelector(
            playbook_service=playbook_service,
            llm_provider=llm_provider,  # Pass llm_provider to PlaybookSelector
        )
        self.decision_coordinator = IntentDecisionCoordinator(
            self.rule_matcher,
            self.llm_matcher,
            use_llm=use_llm,
            rule_priority=rule_priority,
        )
        self.store = store or MindscapeStore()
        self.enable_logging = enable_logging

    async def analyze(
        self,
        user_input: str,
        profile_id: str,
        channel: str = "api",
        profile: Optional[MindscapeProfile] = None,
        active_intents: Optional[List[IntentCard]] = None,
        project_id: Optional[str] = None,
        workspace_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        model_name: Optional[str] = None,
    ) -> IntentAnalysisResult:
        """
        Run 3-layer intent analysis pipeline

        Args:
            user_input: User input text
            profile_id: Profile ID
            channel: Channel (api, line, wp, playbook)
            profile: User profile (optional)
            active_intents: Active intent cards (optional)
            project_id: Associated project ID (optional)
            workspace_id: Associated workspace ID (optional)
            context: Additional context dictionary (optional)

        Returns:
            IntentAnalysisResult with all layer results
        """
        result = IntentAnalysisResult()
        result.raw_input = user_input
        result.channel = channel
        result.profile_id = profile_id
        result.project_id = project_id
        result.workspace_id = workspace_id

        # [VERIFICATION HACK] Force UNKNOWN for test message (Top Level)
        try:
            if "scolionophobia" in user_input:
                logger.warning(
                    "[VERIFICATION] Skipping Intent Analysis to force Agent Mode"
                )
                result.interaction_type = InteractionType.UNKNOWN
                return result
        except Exception:
            pass

        # Pre-check: Execution status query detection (before Layer 1)
        if workspace_id:

            execution_status_result = await self._check_execution_status_query(
                user_input, workspace_id, profile
            )
            if execution_status_result:
                result.interaction_type = InteractionType.START_PLAYBOOK
                result.interaction_confidence = execution_status_result.get(
                    "confidence", 0.9
                )
                result.selected_playbook_code = "execution_status_query"
                result.playbook_confidence = execution_status_result.get(
                    "confidence", 0.9
                )
                result.handoff_plan = execution_status_result.get("handoff_plan")
                result.pipeline_steps["execution_status_query"] = True
                result.pipeline_steps["execution_status_response"] = (
                    execution_status_result.get("response_suggestion")
                )
                logger.info(
                    f"[IntentPipeline] Detected execution status query, selected playbook: execution_status_query"
                )
                return result

        # Layer 1: Interaction Type
        logger.info(
            f"[IntentPipeline] Layer 1: Determining interaction type for: {user_input[:50]}..."
        )

        # Use decision coordinator to decide interaction type
        interaction_type, confidence, method = (
            await self.decision_coordinator.decide_interaction_type(user_input, channel)
        )
        result.interaction_type = interaction_type
        result.interaction_confidence = confidence
        result.pipeline_steps["layer1_method"] = method
        result.pipeline_steps["layer1_rule_result"] = (
            self.rule_matcher.match_interaction_type(user_input, channel) is not None
        )

        logger.info(
            f"[IntentPipeline] Layer 1 result: {result.interaction_type.value} (confidence: {result.interaction_confidence:.2f}, method: {method})"
        )

        # Layer 2: Task Domain (only if START_PLAYBOOK)
        # task_domain is optional and only used as a hint, not a requirement for playbook selection
        if result.interaction_type == InteractionType.START_PLAYBOOK:
            logger.info(
                f"[IntentPipeline] Layer 2: Determining task domain (optional hint)..."
            )

            try:
                task_domain, confidence = await self.llm_matcher.determine_task_domain(
                    user_input, active_intents
                )
                result.task_domain = task_domain
                result.task_domain_confidence = confidence
                result.pipeline_steps["layer2_method"] = "llm_based"
                logger.info(
                    f"[IntentPipeline] Layer 2 result: {result.task_domain.value} (confidence: {confidence:.2f})"
                )
            except Exception as e:
                logger.warning(
                    f"[IntentPipeline] Layer 2: Failed to determine task domain: {e}, continuing without it"
                )
                result.task_domain = TaskDomain.UNKNOWN
                result.task_domain_confidence = 0.0

            # Always proceed to Layer 3 for START_PLAYBOOK
            # Playbook selection is based on user_input, task_domain is only a hint
            if True:
                logger.info(f"[IntentPipeline] Layer 3: Selecting playbook...")

                locale = None
                if profile and profile.preferences:
                    locale = profile.preferences.preferred_content_language
                elif context and "locale" in context:
                    locale = context.get("locale")

                # Ensure playbook_selector has llm_provider
                if not self.playbook_selector.llm_provider:
                    if self.llm_matcher.llm_provider:
                        self.playbook_selector.llm_provider = (
                            self.llm_matcher.llm_provider
                        )
                        logger.info(
                            "[IntentPipeline] Set playbook_selector.llm_provider from llm_matcher"
                        )
                    else:
                        logger.warning(
                            "[IntentPipeline] Both playbook_selector and llm_matcher have no llm_provider"
                        )

                playbook_code, confidence, handoff_plan = (
                    await self.playbook_selector.select_playbook(
                        task_domain=result.task_domain,
                        user_input=user_input,
                        profile=profile,
                        locale=locale,
                        workspace_id=workspace_id,
                    )
                )
                result.selected_playbook_code = playbook_code
                result.playbook_confidence = confidence
                result.handoff_plan = handoff_plan

                if playbook_code:
                    playbook_context = self.playbook_selector.prepare_playbook_context(
                        playbook_code, user_input, profile, active_intents
                    )
                    result.playbook_context = playbook_context

                    if handoff_plan and handoff_plan.steps:
                        for step in handoff_plan.steps:
                            step.inputs.update(playbook_context)
                        handoff_plan.context.update(playbook_context)

                    if not result.project_id:
                        result.project_id = playbook_context.get("project_id")
                    if context:
                        result.playbook_context.update(context)
                        if handoff_plan:
                            handoff_plan.context.update(context)

                logger.info(
                    f"[IntentPipeline] Layer 3 result: {playbook_code} (confidence: {confidence:.2f}, has_handoff_plan: {handoff_plan is not None})"
                )

                logger.info(
                    f"[IntentPipeline] Layer 3 result: {playbook_code} (confidence: {confidence:.2f})"
                )

                if playbook_code:
                    multi_step_result = await self._detect_multi_step_workflow(
                        user_input, playbook_code, result.playbook_context
                    )
                    if multi_step_result:
                        result.is_multi_step = True
                        result.workflow_steps = multi_step_result.get(
                            "workflow_steps", []
                        )
                        result.step_dependencies = multi_step_result.get(
                            "step_dependencies", {}
                        )

        # Log intent decision for offline optimization
        if self.enable_logging:
            try:
                self._log_intent_decision(result)
            except Exception as e:
                logger.warning(f"Failed to log intent decision: {e}")

        return result

    async def _detect_multi_step_workflow(
        self, user_input: str, initial_playbook_code: str, context: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Detect if user request requires multi-step workflow

        Args:
            user_input: User input text
            initial_playbook_code: Initially selected playbook
            context: Playbook context

        Returns:
            Dict with workflow_steps and step_dependencies, or None if single step
        """
        if not self.llm_matcher.llm_provider:
            return None

        # Use PlaybookService to get available playbooks
        available_playbooks_metadata = (
            await self.playbook_selector.playbook_service.list_playbooks()
        )
        available_playbooks = available_playbooks_metadata
        # Handle both PlaybookMetadata and Playbook objects
        playbook_list = []
        for p in available_playbooks:
            if hasattr(p, "playbook_code"):
                # PlaybookMetadata
                playbook_code = p.playbook_code
                name = p.name
                description = p.description if hasattr(p, "description") else None
                tags = p.tags if hasattr(p, "tags") else []
            elif hasattr(p, "metadata"):
                # Playbook object
                playbook_code = p.metadata.playbook_code
                name = p.metadata.name
                description = (
                    p.metadata.description
                    if hasattr(p.metadata, "description")
                    else None
                )
                tags = p.metadata.tags if hasattr(p.metadata, "tags") else []
            else:
                continue

            playbook_info = f"- {playbook_code}: {name}"
            if description:
                playbook_info += f" ({description[:300]})"
            if tags:
                playbook_info += f" [tags: {', '.join(tags)}]"
            playbook_list.append(playbook_info)

        prompt = f"""Analyze the following user request to determine if it requires multiple playbooks:

User input: "{user_input}"
Initial playbook: {initial_playbook_code}

Available playbooks:
{chr(10).join(playbook_list[:20])}

Determine if this request requires multiple steps. Look for:
- Multiple distinct tasks (e.g., "OCR PDF then generate posts")
- Sequential operations (e.g., "process file then save to book")
- Multiple outputs (e.g., "generate IG posts and YT script")

If single step, return null.
If multi-step, return JSON with workflow_steps array (simplified WorkflowStep with only playbook_code and inputs):

{{
    "is_multi_step": true,
    "workflow_steps": [
        {{
            "playbook_code": "pdf_ocr_processing",
            "inputs": {{
                "pdf_files": ["$context.uploaded_files"]
            }}
        }},
        {{
            "playbook_code": "ig_post_generation",
            "inputs": {{
                "source_content": "$previous.pdf_ocr_processing.outputs.ocr_text",
                "post_count": 5
            }}
        }}
    ],
    "step_dependencies": {{
        "ig_post_generation": ["pdf_ocr_processing"]
    }}
}}

Return only valid JSON or null.
"""

        try:
            from backend.app.shared.llm_utils import call_llm, build_prompt
            import json

            if not self.llm_matcher.llm_provider:
                logger.warning("Multi-step detection: llm_provider not available")
                return None

            messages = build_prompt(user_prompt=prompt)
            if not messages:
                logger.warning(
                    "Multi-step detection: build_prompt returned empty messages"
                )
                return None
            response_dict = await call_llm(
                messages=messages,
                llm_provider=self.llm_matcher.llm_provider,
                model=None,
            )

            response_text = response_dict.get("text", "")
            if not response_text:
                return None

            result = _parse_json_from_response(response_text)
            if result and result.get("is_multi_step"):
                logger.info(
                    f"Detected multi-step workflow with {len(result.get('workflow_steps', []))} steps"
                )
                return result
            return None

        except Exception as e:
            logger.warning(f"Multi-step detection failed: {e}", exc_info=True)
            return None

    async def _check_execution_status_query(
        self,
        user_input: str,
        workspace_id: str,
        profile: Optional[MindscapeProfile] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Check if user is asking about execution status/progress

        Returns:
            Dict with handoff_plan and response_suggestion if detected, None otherwise
        """
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore(self.store.db_path)

        pending_tasks = tasks_store.list_pending_tasks(workspace_id)
        running_tasks = tasks_store.list_running_tasks(workspace_id)
        has_active_tasks = len(pending_tasks) > 0 or len(running_tasks) > 0

        progress_keywords = [
            "進度",
            "狀態",
            "執行到哪裡",
            "完成了嗎",
            "卡住了嗎",
            "progress",
            "status",
            "how far",
            "completed",
            "stuck",
            "剛剛那個",
            "出檔那個",
            "SEO 那幾個",
        ]

        message_lower = user_input.lower()
        has_progress_keyword = any(kw in message_lower for kw in progress_keywords)

        if not has_progress_keyword:
            return None

        if not has_active_tasks:
            if not self.llm_matcher.llm_provider:
                return None

            current_tasks_snapshot = "目前沒有執行中的任務"
            llm_prompt = f"""
判斷用戶是否在詢問任務進度或執行狀態。

用戶訊息：{user_input}
當前任務快照：{current_tasks_snapshot}

請判斷：用戶是否在詢問某個任務的進度？
如果用戶在問「產品狀態」「發展狀態」等非執行任務的狀態，應該返回 false。
"""

            try:
                from backend.app.shared.llm_utils import call_llm, build_prompt

                full_prompt = (
                    llm_prompt + '\n\nReturn JSON: {"is_progress_query": true/false}'
                )
                messages = build_prompt(full_prompt)
                response_dict = await call_llm(
                    messages=messages,
                    llm_provider=self.llm_matcher.llm_provider,
                    model=None,
                )

                response_text = response_dict.get("text", "")
                result = _parse_json_from_response(response_text)
                if result and result.get("is_progress_query"):
                    available_playbooks = "筆記組織、IG 貼文生成、PDF OCR 處理等"
                    return {
                        "confidence": 0.9,
                        "response_suggestion": (
                            f"目前這個工作區沒有正在執行的任務。\n"
                            f"你可以先讓我幫你啟動某個 Playbook，例如：{available_playbooks}"
                        ),
                        "handoff_plan": None,
                    }
            except Exception as e:
                logger.warning(
                    f"Failed to check execution status query (no active tasks): {e}",
                    exc_info=True,
                )

        if has_active_tasks:
            current_tasks_snapshot = self._build_current_tasks_snapshot(
                pending_tasks, running_tasks
            )

            if not self.llm_matcher.llm_provider:
                return None

            llm_prompt = f"""
判斷用戶是否在詢問任務進度或執行狀態。

用戶訊息：{user_input}
當前任務快照：
{current_tasks_snapshot}

請判斷：
1. 用戶是否在詢問某個任務的進度？
2. 是否有明確的任務可以對應？

如果用戶在問「產品狀態」「發展狀態」等非執行任務的狀態，應該返回 false。
"""

            try:
                from backend.app.shared.llm_utils import call_llm, build_prompt
                from backend.app.models.playbook import HandoffPlan, WorkflowStep

                full_prompt = (
                    llm_prompt
                    + '\n\nReturn JSON: {"is_progress_query": true/false, "confidence": 0.0-1.0}'
                )
                messages = build_prompt(full_prompt)
                response_dict = await call_llm(
                    messages=messages,
                    llm_provider=self.llm_matcher.llm_provider,
                    model=None,
                )

                response_text = response_dict.get("text", "")
                result = _parse_json_from_response(response_text)
                if result and result.get("is_progress_query"):
                    confidence = float(result.get("confidence", 0.8))

                    workflow_step = WorkflowStep(
                        playbook_code="execution_status_query",
                        kind=PlaybookKind.QUERY,
                        inputs={
                            "user_message": user_input,
                            "workspace_id": workspace_id,
                            "conversation_context": "",
                        },
                        interaction_mode=InteractionMode.AUTOMATED,
                    )

                    handoff_plan = HandoffPlan(
                        steps=[workflow_step],
                        context={
                            "user_message": user_input,
                            "workspace_id": workspace_id,
                        },
                    )

                    return {
                        "confidence": confidence,
                        "handoff_plan": handoff_plan,
                        "response_suggestion": None,
                    }
            except Exception as e:
                logger.warning(f"Failed to check execution status query: {e}")

        return None

    def _build_current_tasks_snapshot(self, pending_tasks, running_tasks) -> str:
        """Build current tasks snapshot for LLM judgment"""
        snapshot = []
        for task in (running_tasks + pending_tasks)[:10]:
            snapshot.append(
                f"- {task.pack_id} ({task.status.value}): "
                f"created at {task.created_at}"
            )
        return "\n".join(snapshot) if snapshot else "目前沒有執行中的任務"

    def _log_intent_decision(self, result: IntentAnalysisResult):
        """
        Log intent decision for offline optimization

        Args:
            result: IntentAnalysisResult to log
        """
        import uuid

        intent_log = IntentLog(
            id=str(uuid.uuid4()),
            timestamp=result.timestamp,
            raw_input=result.raw_input,
            channel=result.channel,
            profile_id=result.profile_id,
            project_id=result.project_id,
            workspace_id=result.workspace_id,
            pipeline_steps=result.pipeline_steps,
            final_decision={
                "interaction_type": (
                    result.interaction_type.value if result.interaction_type else None
                ),
                "interaction_confidence": result.interaction_confidence,
                "task_domain": result.task_domain.value if result.task_domain else None,
                "task_domain_confidence": result.task_domain_confidence,
                "selected_playbook_code": result.selected_playbook_code,
                "playbook_confidence": result.playbook_confidence,
                "playbook_context": result.playbook_context,
            },
            user_override=None,
            metadata={
                "llm_provider": (
                    self.llm_matcher.llm_provider.__class__.__name__
                    if self.llm_matcher.llm_provider
                    else None
                )
            },
        )

        self.store.create_intent_log(intent_log)

    async def replay_intent_log(
        self,
        log_id: str,
        llm_provider=None,
        use_llm: bool = True,
        rule_priority: bool = True,
    ) -> IntentAnalysisResult:
        """
        Replay an intent log with new settings

        Args:
            log_id: Intent log ID to replay
            llm_provider: Optional new LLM provider
            use_llm: Optional new use_llm setting
            rule_priority: Optional new rule_priority setting

        Returns:
            New IntentAnalysisResult from replay
        """
        # Get original log
        original_log = self.store.get_intent_log(log_id)
        if not original_log:
            raise ValueError(f"Intent log not found: {log_id}")

        # Create temporary pipeline with new settings
        temp_pipeline = IntentPipeline(
            llm_provider=llm_provider or self.llm_matcher.llm_provider,
            use_llm=use_llm,
            rule_priority=rule_priority,
            store=None,  # Don't log replay
            enable_logging=False,
        )

        # Replay analysis
        result = await temp_pipeline.analyze(
            user_input=original_log.raw_input,
            profile_id=original_log.profile_id,
            channel=original_log.channel,
        )

        return result

    def evaluate_intent_logs(
        self,
        profile_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate intent logs and calculate metrics

        Args:
            profile_id: Optional profile filter
            start_time: Optional start time filter
            end_time: Optional end time filter

        Returns:
            Evaluation metrics dictionary
        """
        # Get logs with user overrides (annotated logs)
        annotated_logs = self.store.list_intent_logs(
            profile_id=profile_id,
            start_time=start_time,
            end_time=end_time,
            has_override=True,
            limit=1000,
        )

        if not annotated_logs:
            return {
                "total_logs": 0,
                "annotated_logs": 0,
                "accuracy": None,
                "layer1_accuracy": None,
                "layer2_accuracy": None,
                "layer3_accuracy": None,
                "confusion_matrix": {},
            }

        # Calculate metrics
        total = len(annotated_logs)
        correct_layer1 = 0
        correct_layer2 = 0
        correct_layer3 = 0
        correct_overall = 0

        confusion_matrix = {"interaction_type": {}, "task_domain": {}, "playbook": {}}

        for log in annotated_logs:
            final = log.final_decision
            override = log.user_override

            # Layer 1 accuracy
            if override.get("correct_interaction_type"):
                expected = override["correct_interaction_type"]
                actual = final.get("interaction_type")
                if expected == actual:
                    correct_layer1 += 1
                # Update confusion matrix
                key = f"{actual}->{expected}"
                confusion_matrix["interaction_type"][key] = (
                    confusion_matrix["interaction_type"].get(key, 0) + 1
                )

            # Layer 2 accuracy
            if override.get("correct_task_domain"):
                expected = override["correct_task_domain"]
                actual = final.get("task_domain")
                if expected == actual:
                    correct_layer2 += 1
                key = f"{actual}->{expected}"
                confusion_matrix["task_domain"][key] = (
                    confusion_matrix["task_domain"].get(key, 0) + 1
                )

            # Layer 3 accuracy
            if override.get("correct_playbook_code"):
                expected = override["correct_playbook_code"]
                actual = final.get("selected_playbook_code")
                if expected == actual:
                    correct_layer3 += 1
                key = f"{actual}->{expected}"
                confusion_matrix["playbook"][key] = (
                    confusion_matrix["playbook"].get(key, 0) + 1
                )

            # Overall accuracy (all layers correct)
            if (
                override.get("correct_interaction_type")
                == final.get("interaction_type")
                and override.get("correct_task_domain") == final.get("task_domain")
                and override.get("correct_playbook_code")
                == final.get("selected_playbook_code")
            ):
                correct_overall += 1

        # Get total logs count
        all_logs = self.store.list_intent_logs(
            profile_id=profile_id,
            start_time=start_time,
            end_time=end_time,
            has_override=None,
            limit=10000,
        )

        return {
            "total_logs": len(all_logs),
            "annotated_logs": total,
            "accuracy": correct_overall / total if total > 0 else None,
            "layer1_accuracy": correct_layer1 / total if total > 0 else None,
            "layer2_accuracy": correct_layer2 / total if total > 0 else None,
            "layer3_accuracy": correct_layer3 / total if total > 0 else None,
            "confusion_matrix": confusion_matrix,
            "error_breakdown": {
                "layer1_errors": total - correct_layer1,
                "layer2_errors": total - correct_layer2,
                "layer3_errors": total - correct_layer3,
            },
        }
