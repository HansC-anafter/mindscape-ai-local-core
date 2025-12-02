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
from backend.app.shared.llm_utils import call_llm, build_prompt
from backend.app.services.playbook_loader import PlaybookLoader
from backend.app.services.playbook_store import PlaybookStore
from backend.app.services.mindscape_store import MindscapeStore

logger = logging.getLogger(__name__)


class InteractionType(str, Enum):
    """Layer 1: Interaction type classification"""
    QA = "qa"                    # Pure Q&A (no playbook needed)
    START_PLAYBOOK = "start_playbook"  # User wants to start/continue a playbook
    MANAGE_SETTINGS = "manage_settings"  # User wants to manage settings
    UNKNOWN = "unknown"          # Cannot determine


class TaskDomain(str, Enum):
    """Layer 2: Task domain classification"""
    PROPOSAL_WRITING = "proposal_writing"      # Writing proposals, grant applications
    YEARLY_REVIEW = "yearly_review"            # Annual review, yearly book compilation
    HABIT_LEARNING = "habit_learning"          # Habit organization, habit learning
    PROJECT_PLANNING = "project_planning"      # Project planning, task breakdown
    CONTENT_WRITING = "content_writing"         # Content writing, copywriting
    UNKNOWN = "unknown"                         # Unknown domain


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
        r'/start\s+(\w+)',
        r'/start\s+proposal',
        r'/start\s+yearly',
        r'開始\s+(\w+)',
        r'啟動\s+(\w+)',
        r'執行\s+(\w+)',
        r'我想.*寫.*(?:補助|計畫|申請)',
        r'我想.*(?:年度|年終).*(?:回顧|出書)',
        r'幫我.*(?:整理|學習).*(?:習慣)',
    ]

    # Settings management patterns
    SETTINGS_PATTERNS = [
        r'/settings?',
        r'/設定',
        r'設定',
        r'配置',
        r'語言.*設定',
        r'設定.*語言',
        r'preferences?',
        r'settings?',
    ]

    # Export patterns
    EXPORT_PATTERNS = [
        r'匯出',
        r'匯出\s+docx',
        r'匯出\s+markdown',
        r'export',
        r'export\s+docx',
        r'export\s+markdown',
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
                if 'docx' in user_input_lower:
                    return "export_docx"
                elif 'markdown' in user_input_lower:
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

    def match_channel_specific(self, user_input: str, channel: str) -> Optional[InteractionType]:
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
            if user_input_lower.startswith('/'):
                # Extract command after /
                command = user_input_lower[1:].split()[0] if user_input_lower[1:] else ""
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

    def match_interaction_type(self, user_input: str, channel: str = "api") -> Optional[InteractionType]:
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
                logger.warning(f"LLMBasedIntentMatcher received string instead of provider object: {llm_provider[:50]}...")
                self.llm_provider = None
            elif not hasattr(llm_provider, 'chat_completion'):
                logger.warning(f"LLMBasedIntentMatcher received invalid provider type: {type(llm_provider)}")
                self.llm_provider = None
            else:
                self.llm_provider = llm_provider
        else:
            self.llm_provider = None

    async def determine_interaction_type(
        self,
        user_input: str,
        channel: str = "api"
    ) -> tuple[InteractionType, float]:
        """
        Use LLM to determine interaction type (Layer 1)

        Returns:
            (InteractionType, confidence)
        """
        if not self.llm_provider:
            return InteractionType.UNKNOWN, 0.0

        # Double-check provider has required method
        if not hasattr(self.llm_provider, 'chat_completion'):
            logger.error(f"llm_provider does not have chat_completion method: {type(self.llm_provider)}")
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
            response = await call_llm(
                self.llm_provider,
                prompt,
                model="gpt-4o-mini"
            )

            # Parse JSON response
            import json
            result = json.loads(response)

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
        active_intents: Optional[List[IntentCard]] = None
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
            response = await call_llm(
                self.llm_provider,
                prompt,
                model="gpt-4o-mini"
            )

            import json
            result = json.loads(response)

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

        if any(kw in title_lower for kw in ["補助", "申請", "proposal", "申請書", "grant", "application"]):
            return "PROPOSAL_WRITING"
        elif any(kw in title_lower for kw in ["年度", "年終", "yearly", "回顧", "review", "annual"]):
            return "YEARLY_REVIEW"
        elif any(kw in title_lower for kw in ["習慣", "habit"]):
            return "HABIT_LEARNING"
        elif any(kw in title_lower for kw in ["專案", "project", "規劃", "planning"]):
            return "PROJECT_PLANNING"
        else:
            return "CONTENT_WRITING"


class PlaybookSelector:
    """Layer 3: Playbook selection and context preparation"""

    def __init__(self):
        self.playbook_loader = PlaybookLoader()
        self.playbook_store = PlaybookStore()

    def select_playbook(
        self,
        task_domain: TaskDomain,
        user_input: str,
        profile: Optional[MindscapeProfile] = None
    ) -> tuple[Optional[str], float]:
        """
        Select appropriate playbook based on task domain

        Returns:
            (playbook_code, confidence)
        """
        # Domain to playbook mapping - expanded to include more playbooks
        domain_playbook_map = {
            TaskDomain.PROPOSAL_WRITING: "major_proposal_writing",
            TaskDomain.YEARLY_REVIEW: "yearly_personal_book",
            TaskDomain.HABIT_LEARNING: None,  # Habit learning doesn't have a playbook
            TaskDomain.PROJECT_PLANNING: "project_breakdown",  # Use project_breakdown playbook
            TaskDomain.CONTENT_WRITING: "content_drafting",  # Use content_drafting playbook
            TaskDomain.UNKNOWN: None
        }

        playbook_code = domain_playbook_map.get(task_domain)

        if playbook_code:
            # Verify playbook exists
            playbook = self.playbook_loader.get_playbook_by_code(playbook_code)
            if playbook:
                return playbook_code, 0.8
            else:
                logger.warning(f"Playbook {playbook_code} not found")
                return None, 0.0

        return None, 0.0

    def prepare_playbook_context(
        self,
        playbook_code: str,
        user_input: str,
        profile: Optional[MindscapeProfile] = None,
        active_intents: Optional[List[IntentCard]] = None
    ) -> Dict[str, Any]:
        """
        Prepare initial context for playbook execution

        Returns:
            Context dictionary with project_id, locale, etc.
        """
        context = {
            "locale": None,
            "project_id": None,
        }

        # Determine locale from profile
        if profile and profile.preferences:
            context["locale"] = profile.preferences.preferred_content_language or "zh-TW"

        # Try to extract project_id from active intents
        if active_intents:
            # Look for intent with matching tags/category
            for intent in active_intents:
                if intent.metadata and "project_id" in intent.metadata:
                    context["project_id"] = intent.metadata["project_id"]
                    break

        # Extract project hints from user input
        project_match = re.search(r'(?:專案|project)[：:]\s*(\w+)', user_input, re.IGNORECASE)
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
        rule_priority: bool = True
    ):
        self.rule_matcher = rule_matcher
        self.llm_matcher = llm_matcher
        self.use_llm = use_llm
        self.rule_priority = rule_priority

    async def decide_interaction_type(
        self,
        user_input: str,
        channel: str = "api"
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
                logger.info(f"[IntentDecisionCoordinator] Rule-based match: {rule_result.value}")
                return rule_result, 0.9, "rule_based"

        # Fallback to LLM if enabled
        if self.use_llm:
            try:
                interaction_type, confidence = await self.llm_matcher.determine_interaction_type(
                    user_input, channel
                )
                logger.info(f"[IntentDecisionCoordinator] LLM-based match: {interaction_type.value} (confidence: {confidence:.2f})")
                return interaction_type, confidence, "llm_based"
            except Exception as e:
                logger.warning(f"[IntentDecisionCoordinator] LLM matching failed: {e}")

        # If rule_priority is False and no rule match, try rules as fallback
        if not self.rule_priority:
            rule_result = self.rule_matcher.match_interaction_type(user_input, channel)
            if rule_result:
                logger.info(f"[IntentDecisionCoordinator] Rule-based fallback: {rule_result.value}")
                return rule_result, 0.7, "rule_based_fallback"

        # Default: unknown
        logger.warning(f"[IntentDecisionCoordinator] No match found for: {user_input[:50]}")
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
        enable_logging: bool = True
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
        """
        # Override with config if provided
        if config and hasattr(config, 'intent_config'):
            use_llm = config.intent_config.use_llm
            rule_priority = config.intent_config.rule_priority

        self.rule_matcher = RuleBasedIntentMatcher()
        self.llm_matcher = LLMBasedIntentMatcher(llm_provider)
        self.playbook_selector = PlaybookSelector()
        self.decision_coordinator = IntentDecisionCoordinator(
            self.rule_matcher,
            self.llm_matcher,
            use_llm=use_llm,
            rule_priority=rule_priority
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
        context: Optional[Dict[str, Any]] = None
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

        # Layer 1: Interaction Type
        logger.info(f"[IntentPipeline] Layer 1: Determining interaction type for: {user_input[:50]}...")

        # Use decision coordinator to decide interaction type
        interaction_type, confidence, method = await self.decision_coordinator.decide_interaction_type(
            user_input, channel
        )
        result.interaction_type = interaction_type
        result.interaction_confidence = confidence
        result.pipeline_steps["layer1_method"] = method
        result.pipeline_steps["layer1_rule_result"] = self.rule_matcher.match_interaction_type(user_input, channel) is not None

        logger.info(f"[IntentPipeline] Layer 1 result: {result.interaction_type.value} (confidence: {result.interaction_confidence:.2f}, method: {method})")

        # Layer 2: Task Domain (only if START_PLAYBOOK)
        if result.interaction_type == InteractionType.START_PLAYBOOK:
            logger.info(f"[IntentPipeline] Layer 2: Determining task domain...")

            task_domain, confidence = await self.llm_matcher.determine_task_domain(
                user_input, active_intents
            )
            result.task_domain = task_domain
            result.task_domain_confidence = confidence
            result.pipeline_steps["layer2_method"] = "llm_based"

            logger.info(f"[IntentPipeline] Layer 2 result: {result.task_domain.value} (confidence: {confidence:.2f})")

            # Layer 3: Playbook Selection
            if result.task_domain != TaskDomain.UNKNOWN:
                logger.info(f"[IntentPipeline] Layer 3: Selecting playbook...")

                playbook_code, confidence = self.playbook_selector.select_playbook(
                    result.task_domain, user_input, profile
                )
                result.selected_playbook_code = playbook_code
                result.playbook_confidence = confidence

                if playbook_code:
                    result.playbook_context = self.playbook_selector.prepare_playbook_context(
                        playbook_code, user_input, profile, active_intents
                    )
                    # Preserve workspace_id and project_id from input
                    if not result.project_id:
                        result.project_id = result.playbook_context.get("project_id")
                    # Merge context if provided
                    if context:
                        result.playbook_context.update(context)

                logger.info(f"[IntentPipeline] Layer 3 result: {playbook_code} (confidence: {confidence:.2f})")

                if playbook_code:
                    multi_step_result = await self._detect_multi_step_workflow(
                        user_input,
                        playbook_code,
                        result.playbook_context
                    )
                    if multi_step_result:
                        result.is_multi_step = True
                        result.workflow_steps = multi_step_result.get('workflow_steps', [])
                        result.step_dependencies = multi_step_result.get('step_dependencies', {})

        # Log intent decision for offline optimization
        if self.enable_logging:
            try:
                self._log_intent_decision(result)
            except Exception as e:
                logger.warning(f"Failed to log intent decision: {e}")

        return result

    async def _detect_multi_step_workflow(
        self,
        user_input: str,
        initial_playbook_code: str,
        context: Dict[str, Any]
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

        available_playbooks = self.playbook_loader.load_all_playbooks()
        playbook_list = [
            f"- {p.metadata.playbook_code}: {p.metadata.name}"
            for p in available_playbooks
        ]

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
            from backend.app.shared.llm_utils import call_llm
            import json

            response = await call_llm(
                self.llm_matcher.llm_provider,
                prompt,
                model="gpt-4o-mini"
            )

            result = json.loads(response.strip())
            if result.get('is_multi_step'):
                logger.info(f"Detected multi-step workflow with {len(result.get('workflow_steps', []))} steps")
                return result
            return None

        except Exception as e:
            logger.warning(f"Multi-step detection failed: {e}")
            return None

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
                "interaction_type": result.interaction_type.value if result.interaction_type else None,
                "interaction_confidence": result.interaction_confidence,
                "task_domain": result.task_domain.value if result.task_domain else None,
                "task_domain_confidence": result.task_domain_confidence,
                "selected_playbook_code": result.selected_playbook_code,
                "playbook_confidence": result.playbook_confidence,
                "playbook_context": result.playbook_context
            },
            user_override=None,
            metadata={
                "llm_provider": self.llm_matcher.llm_provider.__class__.__name__ if self.llm_matcher.llm_provider else None
            }
        )

        self.store.create_intent_log(intent_log)

    async def replay_intent_log(
        self,
        log_id: str,
        llm_provider=None,
        use_llm: bool = True,
        rule_priority: bool = True
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
            enable_logging=False
        )

        # Replay analysis
        result = await temp_pipeline.analyze(
            user_input=original_log.raw_input,
            profile_id=original_log.profile_id,
            channel=original_log.channel
        )

        return result

    def evaluate_intent_logs(
        self,
        profile_id: Optional[str] = None,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
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
            limit=1000
        )

        if not annotated_logs:
            return {
                "total_logs": 0,
                "annotated_logs": 0,
                "accuracy": None,
                "layer1_accuracy": None,
                "layer2_accuracy": None,
                "layer3_accuracy": None,
                "confusion_matrix": {}
            }

        # Calculate metrics
        total = len(annotated_logs)
        correct_layer1 = 0
        correct_layer2 = 0
        correct_layer3 = 0
        correct_overall = 0

        confusion_matrix = {
            "interaction_type": {},
            "task_domain": {},
            "playbook": {}
        }

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
                confusion_matrix["interaction_type"][key] = confusion_matrix["interaction_type"].get(key, 0) + 1

            # Layer 2 accuracy
            if override.get("correct_task_domain"):
                expected = override["correct_task_domain"]
                actual = final.get("task_domain")
                if expected == actual:
                    correct_layer2 += 1
                key = f"{actual}->{expected}"
                confusion_matrix["task_domain"][key] = confusion_matrix["task_domain"].get(key, 0) + 1

            # Layer 3 accuracy
            if override.get("correct_playbook_code"):
                expected = override["correct_playbook_code"]
                actual = final.get("selected_playbook_code")
                if expected == actual:
                    correct_layer3 += 1
                key = f"{actual}->{expected}"
                confusion_matrix["playbook"][key] = confusion_matrix["playbook"].get(key, 0) + 1

            # Overall accuracy (all layers correct)
            if (override.get("correct_interaction_type") == final.get("interaction_type") and
                override.get("correct_task_domain") == final.get("task_domain") and
                override.get("correct_playbook_code") == final.get("selected_playbook_code")):
                correct_overall += 1

        # Get total logs count
        all_logs = self.store.list_intent_logs(
            profile_id=profile_id,
            start_time=start_time,
            end_time=end_time,
            has_override=None,
            limit=10000
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
                "layer3_errors": total - correct_layer3
            }
        }
