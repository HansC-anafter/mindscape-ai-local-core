"""
Context Builder Service

Builds context for LLM prompts from workspace data:
- Recent file analysis results
- Timeline items (pack execution results)
- Recent conversation history
"""

import logging
import os
from typing import Dict, Any, List, Optional, Tuple
from datetime import datetime

try:
    import tiktoken
    TIKTOKEN_AVAILABLE = True
except ImportError:
    TIKTOKEN_AVAILABLE = False

from .model_context_presets import get_context_preset, get_model_name_from_env
from .pack_info_collector import PackInfoCollector

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Build context for LLM prompts from workspace data"""

    def __init__(
        self,
        store=None,
        timeline_items_store=None,
        model_name: Optional[str] = None
    ):
        """
        Initialize ContextBuilder

        Args:
            store: MindscapeStore instance
            timeline_items_store: TimelineItemsStore instance
            model_name: Optional model name for context preset selection
                       If None, will try to get from environment variables
        """
        self.store = store
        self.timeline_items_store = timeline_items_store

        if not model_name:
            model_name = get_model_name_from_env()

        self.model_name = model_name
        self.preset = get_context_preset(model_name)

        logger.info(f"ContextBuilder initialized with model: {model_name or 'default'}, preset: MAX_EVENTS={self.preset['MAX_EVENTS_FOR_QUERY']}, MAX_MESSAGES={self.preset['MAX_HISTORY_MESSAGES']}, MAX_CHARS={self.preset['MAX_MESSAGE_CHARS']}")

    async def build_qa_context(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        hours: int = 24
    ) -> str:
        """
        Build context string for QA mode LLM prompts

        Args:
            workspace_id: Workspace ID
            message: User message
            profile_id: Optional profile ID for retrieving intents
            workspace: Optional workspace object for metadata
            hours: Hours to look back for context (default 24)

        Returns:
            Context string to inject into LLM prompt
        """
        context_parts = []

        # Workspace metadata - highest priority context
        if workspace:
            workspace_info = []
            if workspace.title:
                workspace_info.append(f"Title: {workspace.title}")
            if workspace.description:
                workspace_info.append(f"Description: {workspace.description}")
            if workspace.mode:
                workspace_info.append(f"Mode: {workspace.mode}")
            if workspace_info:
                context_parts.append("\n## Workspace Context:")
                context_parts.extend(workspace_info)
                logger.info(f"Injected workspace metadata into QA context: {workspace.title or workspace_id}")

        # Active intents - current goals and objectives
        if profile_id and self.store:
            try:
                from ...models.mindscape import IntentStatus
                active_intents = self.store.list_intents(
                    profile_id=profile_id,
                    status=IntentStatus.ACTIVE
                )
                if active_intents:
                    context_parts.append("\n## Active Intents (Current Goals):")
                    for intent in active_intents[:10]:
                        intent_info = f"- {intent.title}"
                        if intent.description:
                            intent_info += f": {intent.description[:150]}"
                        if intent.priority:
                            intent_info += f" [Priority: {intent.priority.value}]"
                        if intent.progress_percentage is not None:
                            intent_info += f" [Progress: {intent.progress_percentage:.0f}%]"
                        context_parts.append(intent_info)
                    logger.info(f"Injected {len(active_intents)} active intents into QA context")
            except Exception as e:
                logger.warning(f"Failed to get active intents: {e}")

        # Current tasks - what's in progress (with Intent links)
        if self.store:
            try:
                from ..stores.tasks_store import TasksStore
                from ...models.workspace import TaskStatus
                tasks_store = TasksStore(self.store.db_path)

                pending_tasks = tasks_store.list_pending_tasks(workspace_id)
                running_tasks = tasks_store.list_running_tasks(workspace_id)

                if pending_tasks or running_tasks:
                    context_parts.append("\n## Current Tasks:")

                    # Group tasks by intent if possible
                    tasks_by_intent = {}
                    unlinked_tasks = []

                    for task in (running_tasks + pending_tasks)[:10]:
                        # Try to find associated intent
                        intent_title = None
                        if hasattr(task, 'intent_id') and task.intent_id:
                            try:
                                intent = self.store.get_intent(task.intent_id)
                                if intent:
                                    intent_title = intent.title
                            except Exception:
                                pass

                        task_status = task.status.value if hasattr(task.status, 'value') else str(task.status)
                        task_info = f"- {task.pack_id} ({task_status})"
                        if task.task_type:
                            task_info += f": {task.task_type}"
                        if task.params and isinstance(task.params, dict):
                            source = task.params.get('source', '')
                            if source:
                                task_info += f" [Source: {source}]"

                        if intent_title:
                            if intent_title not in tasks_by_intent:
                                tasks_by_intent[intent_title] = []
                            tasks_by_intent[intent_title].append(task_info)
                        else:
                            unlinked_tasks.append(task_info)

                    # Format tasks grouped by intent
                    for intent_title, task_list in tasks_by_intent.items():
                        context_parts.append(f"\n  Under Intent: {intent_title}")
                        context_parts.extend([f"    {task}" for task in task_list])

                    # Add unlinked tasks
                    if unlinked_tasks:
                        context_parts.extend(unlinked_tasks)

                    logger.info(f"Injected {len(pending_tasks) + len(running_tasks)} current tasks into QA context (grouped by {len(tasks_by_intent)} intents)")
            except Exception as e:
                logger.warning(f"Failed to get current tasks: {e}")

        # Recent files - try to get from file analysis results
        try:
            # Get recent file events from workspace
            if self.store:
                recent_events = self.store.get_events_by_workspace(
                    workspace_id=workspace_id,
                    limit=50
                )
                file_events = []
                for event in recent_events:
                    if hasattr(event, 'event_type') and event.event_type.value == 'file_analysis':
                        payload = event.payload if isinstance(event.payload, dict) else {}
                        metadata = event.metadata if isinstance(event.metadata, dict) else {}
                        file_analysis = metadata.get('file_analysis', {})
                        if file_analysis:
                            file_events.append({
                                'name': payload.get('filename', 'Unknown'),
                                'analysis_summary': file_analysis.get('analysis', {}).get('summary', ''),
                                'themes': file_analysis.get('analysis', {}).get('themes', [])
                            })

                if file_events:
                    context_parts.append("\n## Recent Files:")
                    for file_ctx in file_events[:3]:
                        file_info = f"- {file_ctx.get('name', 'Unknown')}"
                        if file_ctx.get('analysis_summary'):
                            file_info += f" ({file_ctx.get('analysis_summary')[:100]})"
                        if file_ctx.get('themes'):
                            file_info += f"\n  Themes: {', '.join(file_ctx.get('themes', [])[:5])}"
                        context_parts.append(file_info)
        except Exception as e:
            logger.warning(f"Failed to get file context: {e}")

        try:
            if self.timeline_items_store:
                recent_timeline_items = self.timeline_items_store.list_timeline_items_by_workspace(
                    workspace_id=workspace_id,
                    limit=30
                )
                if recent_timeline_items:
                    context_parts.append("\n## Recent Timeline Activity:")
                    for item in recent_timeline_items[:30]:
                        item_type = item.type.value if hasattr(item.type, 'value') else str(item.type)
                        item_info = f"- {item_type}: {item.title}"
                        if item.summary:
                            item_info += f" - {item.summary[:200]}"
                        context_parts.append(item_info)
                    logger.info(f"Injected {len(recent_timeline_items)} timeline items into QA context")
        except Exception as e:
            logger.error(f"Failed to get timeline context: {e}", exc_info=True)

        try:
            if self.store:
                max_events = self.preset["MAX_EVENTS_FOR_QUERY"]
                max_messages = self.preset["MAX_HISTORY_MESSAGES"]
                max_chars = self.preset["MAX_MESSAGE_CHARS"]

                # Get conversation history with summary support
                conversation_context, summary_context = await self._get_conversation_history_with_summary(
                    workspace_id=workspace_id,
                    max_events=max_events,
                    max_messages=max_messages,
                    max_chars=max_chars
                )

                # Add summary if available
                if summary_context:
                    context_parts.append("\n## Conversation Summary (Earlier Context):")
                    context_parts.append(summary_context)
                    logger.info("Injected conversation summary into QA context")

                # Add recent messages
                if conversation_context:
                    context_parts.append("\n## Recent Conversation:")
                    context_parts.extend(conversation_context)
                    logger.info(f"Injected {len(conversation_context)} conversation messages into QA context (preset: max_messages={max_messages}, max_chars={max_chars})")
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}", exc_info=True)

        # Add long-term memory context (RAG)
        try:
            long_term_memory = await self._get_long_term_memory_context(
                workspace_id=workspace_id,
                message=message,
                profile_id=profile_id
            )
            if long_term_memory:
                context_parts.append("\n## Long-term Knowledge:")
                context_parts.append(long_term_memory)
                logger.info("Injected long-term memory context into QA context")
        except Exception as e:
            logger.debug(f"Failed to get long-term memory context: {e}")

        # Join all context parts and return
        return "\n".join(context_parts) if context_parts else ""

    async def _get_conversation_history_with_summary(
        self,
        workspace_id: str,
        max_events: int,
        max_messages: int,
        max_chars: int
    ) -> Tuple[List[str], Optional[str]]:
        """
        Get conversation history with sliding window and summary support

        Returns:
            Tuple of (recent_messages, summary_text)
        """
        try:
            recent_events = self.store.get_events_by_workspace(
                workspace_id=workspace_id,
                limit=max_events
            )

            # Separate message events and summary events
            message_events = []
            summary_events = []

            for event in recent_events:
                if hasattr(event, 'event_type'):
                    event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)
                    if event_type == 'message':
                        message_events.append(event)
                    elif event_type == 'summary' or event_type == 'insight':
                        # Check if it's a summary event (either type is 'summary' or metadata has is_summary flag)
                        is_summary = False
                        if event_type == 'summary':
                            is_summary = True
                        elif hasattr(event, 'metadata') and isinstance(event.metadata, dict):
                            is_summary = event.metadata.get('is_summary', False)

                        if is_summary:
                            summary_events.append(event)

            # Get most recent summary (if exists)
            summary_text = None
            if summary_events:
                latest_summary = summary_events[0]  # Assuming sorted by time
                payload = latest_summary.payload if isinstance(latest_summary.payload, dict) else {}
                summary_text = payload.get('summary', '') or payload.get('content', '')
                if summary_text:
                    summary_text = summary_text[:1000]  # Limit summary length

            # Process message events
            conversation_context = []
            for event in message_events:
                payload = event.payload if isinstance(event.payload, dict) else {}
                msg = payload.get('message', '')
                actor = event.actor.value if hasattr(event.actor, 'value') else str(event.actor)
                if msg and actor in ['user', 'assistant']:
                    role = 'User' if actor == 'user' else 'Assistant'
                    truncated_msg = msg[:max_chars] if len(msg) > max_chars else msg

                    # Filter out generic welcome/suggestion messages that pollute context
                    # These are generic responses that don't provide useful context
                    generic_patterns = [
                        "I can help you:",
                        "Execute Playbook workflows",
                        "Quick start:",
                        "Suggestion:",
                        "If this is your first time",
                        "Let me know what you need help with",
                        "can help you:",
                        "我可以幫助你",
                        "快速開始",
                        "建議"
                    ]
                    # Skip generic welcome messages
                    if role == 'Assistant':
                        msg_lower = truncated_msg.lower()
                        # Check if message contains generic patterns
                        has_generic = any(pattern.lower() in msg_lower for pattern in generic_patterns)
                        if has_generic:
                            # Calculate generic content ratio
                            generic_chars = sum(len(p) for p in generic_patterns if p.lower() in msg_lower)
                            total_chars = len(truncated_msg)
                            # Skip if more than 30% generic content OR if message is primarily generic
                            if total_chars > 0 and (generic_chars > total_chars * 0.3 or generic_chars > 100):
                                logger.info(f"Filtered out generic Assistant message (generic_chars={generic_chars}, total_chars={total_chars}): {truncated_msg[:200]}...")
                                continue

                    conversation_context.append(f"{role}: {truncated_msg}")

            # Apply sliding window: keep only most recent messages
            messages_to_keep = conversation_context[-max_messages:]

            # Check if summary should be triggered using multi-factor policy
            should_summarize_flag, summary_reason = await self.should_summarize(
                workspace_id=workspace_id,
                conversation_context=conversation_context,
                recent_events=recent_events
            )

            if should_summarize_flag:
                # Get messages that will be excluded (oldest messages)
                # Keep recent messages, summarize the rest
                summary_threshold = min(30, max(int(max_messages * 0.3), 20))
                messages_to_summarize = conversation_context[:-summary_threshold] if len(conversation_context) > summary_threshold else []

                if len(messages_to_summarize) >= 5:  # Only summarize if we have at least 5 old messages
                    # Check if we already have a recent summary (within last 50 events)
                    # If not, generate one
                    summary_generated = False
                    if not summary_events or len(summary_events) == 0:
                        try:
                            await self._generate_and_store_summary(
                                workspace_id=workspace_id,
                                messages_to_summarize=messages_to_summarize,
                                profile_id=getattr(self, 'profile_id', None),
                                summary_type='HISTORY_SUMMARY' if 'capacity' in summary_reason.lower() else 'EPISODE_SUMMARY'
                            )
                            summary_generated = True
                            logger.info(f"Auto-generated summary ({summary_reason}) for {len(messages_to_summarize)} old messages (threshold: {summary_threshold}, total: {len(conversation_context)})")
                        except Exception as e:
                            logger.error(f"Failed to auto-generate summary: {e}")
                            # Do not silently truncate - let the error propagate
                            # The system should fail properly rather than degrade silently
                            raise

                    # If summary was generated successfully, the old messages are already excluded
                    # by the summary, so we can return the recent messages
                    if summary_generated:
                        messages_to_keep = conversation_context[-summary_threshold:]
                        return messages_to_keep, summary_text

            return messages_to_keep, summary_text

        except Exception as e:
            logger.warning(f"Failed to get conversation history with summary: {e}")
            return [], None

    async def should_summarize(
        self,
        workspace_id: str,
        conversation_context: List[str],
        recent_events: List[Any]
    ) -> Tuple[bool, str]:
        """
        Determine if summary should be triggered using multi-factor policy

        Score = 0.5 * capacity_score + 0.3 * structure_score + 0.2 * salience_score
        Returns True if score >= 0.7

        Args:
            workspace_id: Workspace ID
            conversation_context: List of conversation messages
            recent_events: Recent mind events

        Returns:
            Tuple of (should_summarize, reason)
        """
        # Capacity-based score (0~1)
        capacity_score = await self._calculate_capacity_score(conversation_context)

        # Structure-based score (0 or 1)
        structure_score, structure_reason = await self._detect_episode_boundary(workspace_id, recent_events)

        # Salience-based score (0~1)
        salience_score = await self._calculate_salience_score(conversation_context, recent_events)

        # Weighted composite score
        composite_score = (
            0.5 * capacity_score +
            0.3 * structure_score +
            0.2 * salience_score
        )

        # Trigger if composite score >= 0.7 OR capacity score >= 0.9 (critical)
        should_summarize = composite_score >= 0.7 or capacity_score >= 0.9

        # Build reason string
        reasons = []
        if capacity_score >= 0.9:
            reasons.append(f"capacity_critical({capacity_score:.2f})")
        elif capacity_score > 0.7:
            reasons.append(f"capacity({capacity_score:.2f})")
        if structure_score > 0:
            reasons.append(f"structure({structure_reason})")
        if salience_score > 0.7:
            reasons.append(f"salience({salience_score:.2f})")

        reason = " + ".join(reasons) if reasons else f"composite({composite_score:.2f})"

        # Log summary decision for debugging
        logger.info(f"Summary decision: should_summarize={should_summarize}, composite_score={composite_score:.3f}, capacity={capacity_score:.3f}, structure={structure_score:.3f}, salience={salience_score:.3f}, reason={reason}")

        return should_summarize, reason

    async def _calculate_capacity_score(self, conversation_context: List[str]) -> float:
        """
        Calculate capacity-based score (0~1)
        Higher score means context is approaching limit

        Args:
            conversation_context: List of conversation messages

        Returns:
            Capacity score (0~1)
        """
        if not conversation_context:
            return 0.0

        # Estimate total token count
        total_text = "\n".join(conversation_context)
        estimated_tokens = self.estimate_token_count(total_text, self.model_name)

        # Get model's actual context limit (not just history budget)
        # Use the model's max context window, reserve 20% for output
        model_max_tokens = 16385  # Default to gpt-3.5-turbo limit (based on actual errors)
        if hasattr(self, 'model_name') and self.model_name:
            # Try to get actual model limit from preset
            from .model_context_presets import get_context_preset
            try:
                model_preset = get_context_preset(self.model_name)
                model_max_tokens = model_preset.get('MAX_CONTEXT_TOKENS', model_max_tokens)
            except Exception:
                pass  # Fallback to default

        # Reserve 20% for output, so effective input limit is 80%
        effective_limit = int(model_max_tokens * 0.8)

        # Calculate ratio (0~1, where 1 means at limit)
        # Trigger summarization when we reach 70% of effective limit
        ratio = min(1.0, estimated_tokens / (effective_limit * 0.7))

        logger.debug(f"Capacity score calculation: estimated_tokens={estimated_tokens}, model_max={model_max_tokens}, effective_limit={effective_limit}, ratio={ratio:.3f}")

        return ratio

    async def _detect_episode_boundary(
        self,
        workspace_id: str,
        recent_events: List[Any]
    ) -> Tuple[float, str]:
        """
        Detect episode boundary signals (0 or 1)

        Triggers:
        - High-level Task completed (TASK_COMPLETED with high importance)
        - Intent status transition: in_progress → paused/done
        - User ending phrases: "好，那今天先到這裡", "這版當成 v1，大致 ok"
        - Workspace mode switch

        Args:
            workspace_id: Workspace ID
            recent_events: Recent mind events

        Returns:
            Tuple of (score, reason)
        """
        if not recent_events:
            return 0.0, ""

        # Check last few events for boundary signals
        for event in recent_events[-5:]:  # Check last 5 events
            if not hasattr(event, 'event_type'):
                continue

            event_type = event.event_type.value if hasattr(event.event_type, 'value') else str(event.event_type)

            # Task completed with high importance
            if event_type == 'task_completed':
                payload = event.payload if isinstance(event.payload, dict) else {}
                importance = payload.get('importance', 0.5)
                if importance > 0.7:
                    return 1.0, "task_completed_high_importance"

            # Intent status change
            if event_type == 'intent_updated':
                payload = event.payload if isinstance(event.payload, dict) else {}
                old_status = payload.get('old_status', '')
                new_status = payload.get('new_status', '')
                if old_status == 'in_progress' and new_status in ['paused', 'done', 'completed']:
                    return 1.0, f"intent_{new_status}"

            # User ending phrases (check message events)
            if event_type == 'message':
                payload = event.payload if isinstance(event.payload, dict) else {}
                message = payload.get('message', '')
                if message:
                    ending_phrases = [
                        "好，那今天先到這裡",
                        "這版當成 v1",
                        "大致 ok",
                        "先這樣",
                        "今天就到這裡",
                        "先告一段落"
                    ]
                    message_lower = message.lower()
                    if any(phrase in message_lower for phrase in ending_phrases):
                        return 1.0, "user_ending_phrase"

        return 0.0, ""

    async def _calculate_salience_score(
        self,
        conversation_context: List[str],
        recent_events: List[Any]
    ) -> float:
        """
        Calculate salience score based on importance indicators (0~1)

        Indicators:
        - Stable preferences (writing style, work habits)
        - Persistent settings (course goals, learner profiles)
        - Key decisions ("we'll use option B")

        Args:
            conversation_context: List of conversation messages
            recent_events: Recent mind events

        Returns:
            Salience score (0~1)
        """
        if not conversation_context:
            return 0.0

        # Check recent messages for importance indicators
        recent_text = "\n".join(conversation_context[-10:])  # Last 10 messages
        recent_text_lower = recent_text.lower()

        importance_keywords = [
            "決定", "決定用", "就用", "固定", "以後都", "最終版本",
            "決定", "決定用", "就用", "固定", "以後都", "最終版本",
            "preference", "always", "never", "decided", "final", "permanent"
        ]

        keyword_count = sum(1 for keyword in importance_keywords if keyword in recent_text_lower)

        # Normalize to 0~1 (more keywords = higher score)
        max_keywords = 5
        salience_score = min(1.0, keyword_count / max_keywords)

        return salience_score

    async def _generate_and_store_summary(
        self,
        workspace_id: str,
        messages_to_summarize: List[str],
        profile_id: Optional[str] = None,
        summary_type: str = 'HISTORY_SUMMARY'
    ):
        """
        Generate summary for old conversation messages and store as event

        Args:
            workspace_id: Workspace ID
            messages_to_summarize: List of message strings to summarize
            profile_id: Profile ID (optional)
        """
        try:
            from ..agent_runner import LLMProviderManager
            from ...models.mindscape import MindEvent, EventType, EventActor
            from datetime import datetime
            import uuid

            # Combine messages into a single text
            conversation_text = "\n".join(messages_to_summarize)

            # Generate summary using LLM
            # Use the same API key source as main LLM calls (ConfigStore, not just env var)
            from ..config_store import ConfigStore
            import os

            config_store = ConfigStore()
            config = config_store.get_or_create_config(profile_id or "default-user")

            # Get API key from config (same as main LLM calls) or fallback to env
            openai_key = None
            if hasattr(config, 'agent_backend') and hasattr(config.agent_backend, 'openai_api_key'):
                openai_key = config.agent_backend.openai_api_key
            elif isinstance(config, dict):
                openai_key = config.get('openai_api_key')

            if not openai_key:
                openai_key = os.getenv("OPENAI_API_KEY")

            if not openai_key or openai_key == "your-openai-api-key-here":
                logger.error(f"Invalid or missing OpenAI API key for summary generation. Config has key: {bool(openai_key and openai_key != 'your-openai-api-key-here')}")
                raise ValueError("OpenAI API key is not configured or is invalid")

            llm_manager = LLMProviderManager(openai_key=openai_key)
            provider = llm_manager.get_provider()
            if not provider:
                logger.error("No LLM provider available for summary generation")
                raise ValueError("No LLM provider available")

            summary_prompt = f"""請為以下對話歷史生成一個簡潔的摘要，重點包括：
1. 用戶的主要目標和需求
2. 已完成的進度和成果
3. 待解決的問題或下一步行動

對話歷史：
{conversation_text[:5000]}  # Limit to 5000 chars for summary generation

請用中文生成摘要，控制在 300 字以內。"""

            # Use chat_completion with messages format
            messages = [
                {"role": "system", "content": "你是一個專業的對話摘要助手，擅長提取關鍵信息和進度。"},
                {"role": "user", "content": summary_prompt}
            ]

            summary_text = await provider.chat_completion(
                messages=messages,
                model=self.model_name or "gpt-4o-mini",
                max_tokens=500,
                temperature=0.3
            )

            summary_text = summary_text.strip() if summary_text else ""

            if not summary_text or len(summary_text) < 50:
                logger.warning("Generated summary is too short, skipping storage")
                return

            # Create summary event
            summary_event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=datetime.now(),
                actor=EventActor.SYSTEM,
                channel="workspace",
                profile_id=profile_id or "default-user",
                workspace_id=workspace_id,
                event_type=EventType.INSIGHT,  # Use INSIGHT type for summary
                payload={
                    "summary": summary_text,
                    "content": summary_text,
                    "message_count": len(messages_to_summarize),
                    "auto_generated": True,
                    "summary_type": summary_type
                },
                metadata={
                    "is_summary": True,
                    "summary_type": summary_type.lower()
                }
            )

            # Store the event with embedding generation (as per documentation requirement)
            # Generate summary for oldest messages and store as SUMMARY event
            self.store.create_event(summary_event, generate_embedding=True)
            logger.info(f"Stored auto-generated summary event with embedding for workspace {workspace_id}")

        except Exception as e:
            logger.error(f"Failed to generate and store summary: {e}", exc_info=True)
            raise

    async def _get_multi_scope_memory(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        intent_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get hierarchical memory context from multiple scopes (Global/Workspace/Intent)

        Args:
            workspace_id: Workspace ID
            message: Current user message
            profile_id: User profile ID
            intent_id: Optional active intent ID

        Returns:
            Formatted hierarchical memory context string or None
        """
        try:
            from ..vector_search import VectorSearchService

            # Check if vector DB is available
            search_service = VectorSearchService()
            if not await search_service.check_connection():
                return None

            # Build query from current message + active intent titles
            query_parts = [message]

            if profile_id and self.store:
                try:
                    from ...models.mindscape import IntentStatus
                    active_intents = self.store.list_intents(
                        profile_id=profile_id,
                        status=IntentStatus.ACTIVE
                    )
                    if active_intents:
                        intent_titles = [intent.title for intent in active_intents[:3]]
                        query_parts.extend(intent_titles)
                        # Use first active intent if intent_id not provided
                        if not intent_id and active_intents:
                            intent_id = active_intents[0].id
                except Exception:
                    pass

            query = " ".join(query_parts)

            # Determine retrieval plan based on context
            # Default: workspace general chat
            scopes = ['global', 'workspace']
            top_k_per_scope = {
                'global': 3,
                'workspace': 8
            }

            # If intent_id provided, add intent scope
            if intent_id:
                scopes.append('intent')
                top_k_per_scope['intent'] = 8

            # Perform multi-scope search
            logger.info(f"Multi-scope memory search: query='{query[:100]}...', scopes={scopes}, top_k={top_k_per_scope}")
            multi_scope_results = await search_service.multi_scope_search(
                query=query,
                user_id=profile_id or "default_user",
                workspace_id=workspace_id,
                intent_id=intent_id,
                scopes=scopes,
                top_k_per_scope=top_k_per_scope
            )

            # Log results
            total_results = sum(len(results) for results in multi_scope_results.values())
            logger.info(f"Multi-scope memory search results: total={total_results}, global={len(multi_scope_results.get('global', []))}, workspace={len(multi_scope_results.get('workspace', []))}, intent={len(multi_scope_results.get('intent', []))}")

            # Format results by scope
            formatted_parts = []

            # Global scope
            if 'global' in multi_scope_results and multi_scope_results['global']:
                formatted_parts.append("## Global User / System Profile:")
                for result in multi_scope_results['global']:
                    content = result.get('content', '') or result.get('text', '')
                    if content:
                        formatted_parts.append(f"- {content[:300]}")

                # Update last_used_at for retrieved records
                record_ids = [str(r.get('id', '')) for r in multi_scope_results['global'] if r.get('id')]
                if record_ids:
                    await search_service.update_last_used_at(record_ids)

            # Workspace scope
            if 'workspace' in multi_scope_results and multi_scope_results['workspace']:
                formatted_parts.append("\n## This Workspace:")
                for result in multi_scope_results['workspace']:
                    content = result.get('content', '') or result.get('text', '')
                    if content:
                        formatted_parts.append(f"- {content[:300]}")

                # Update last_used_at
                record_ids = [str(r.get('id', '')) for r in multi_scope_results['workspace'] if r.get('id')]
                if record_ids:
                    await search_service.update_last_used_at(record_ids)

            # Intent scope
            if 'intent' in multi_scope_results and multi_scope_results['intent']:
                formatted_parts.append("\n## Current Intent:")
                for result in multi_scope_results['intent']:
                    content = result.get('content', '') or result.get('text', '')
                    if content:
                        formatted_parts.append(f"- {content[:300]}")

                # Update last_used_at
                record_ids = [str(r.get('id', '')) for r in multi_scope_results['intent'] if r.get('id')]
                if record_ids:
                    await search_service.update_last_used_at(record_ids)

            if formatted_parts:
                return "\n".join(formatted_parts)

            return None

        except Exception as e:
            logger.debug(f"Multi-scope memory retrieval failed: {e}")
            return None

    async def _get_long_term_memory_context(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None
    ) -> Optional[str]:
        """
        Get long-term memory context from pgvector using semantic search
        (Legacy method - now uses multi-scope search)

        Args:
            workspace_id: Workspace ID
            message: Current user message
            profile_id: User profile ID

        Returns:
            Long-term memory context string or None
        """
        # Use new multi-scope memory method
        return await self._get_multi_scope_memory(
            workspace_id=workspace_id,
            message=message,
            profile_id=profile_id
        )

    def estimate_token_count(self, text: str, model_name: Optional[str] = None) -> int:
        """
        Estimate token count for a given text using tiktoken

        Args:
            text: Text to estimate tokens for
            model_name: Model name to use for encoding (defaults to self.model_name or cl100k_base)

        Returns:
            Estimated token count
        """
        if not text:
            return 0

        if not TIKTOKEN_AVAILABLE:
            return len(text.split()) * 2

        try:
            model_name = model_name or self.model_name or "gpt-4"
            encoding_name = "cl100k_base"
            if "gpt-4" in model_name.lower() or "gpt-3.5" in model_name.lower():
                encoding_name = "cl100k_base"
            elif "o1" in model_name.lower() or "o3" in model_name.lower():
                encoding_name = "o200k_base"

            encoding = tiktoken.get_encoding(encoding_name)
            return len(encoding.encode(text))
        except Exception as e:
            logger.warning(f"Failed to estimate token count with tiktoken: {e}, falling back to word count")
            return len(text.split()) * 2

    async def build_qa_context_with_token_count(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        hours: int = 24
    ) -> Tuple[str, int]:
        """
        Build context string and return token count

        Returns:
            Tuple of (context_string, token_count)
        """
        context = await self.build_qa_context(
            workspace_id=workspace_id,
            message=message,
            profile_id=profile_id,
            workspace=workspace,
            hours=hours
        )
        enhanced_prompt = self.build_enhanced_prompt(message=message, context=context)
        token_count = self.estimate_token_count(enhanced_prompt, self.model_name)
        return context, token_count

    async def build_planning_context(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        target_tokens: Optional[int] = None,
        mode: str = "planning"
    ) -> str:
        """
        Build structured context specifically for planning tasks

        Args:
            workspace_id: Workspace ID
            message: User message
            profile_id: Optional profile ID for retrieving intents
            workspace: Optional workspace object for metadata
            target_tokens: Target token budget for the context (if None, uses default preset)
            mode: Context mode ("planning" or "qa")

        Returns:
            Structured context string optimized for planning tasks
        """
        context_parts = []

        if target_tokens is None:
            model_max_tokens = 16385
            if hasattr(self, 'model_name') and self.model_name:
                from .model_context_presets import get_context_preset
                try:
                    model_preset = get_context_preset(self.model_name)
                    model_max_tokens = model_preset.get('MAX_CONTEXT_TOKENS', model_max_tokens)
                except Exception:
                    pass
            target_tokens = int(model_max_tokens * 0.6)

        logger.info(f"Building planning context with target_tokens={target_tokens}, mode={mode}")

        workspace_profile = []
        if workspace:
            if workspace.title:
                workspace_profile.append(f"Title: {workspace.title}")
            if workspace.description:
                workspace_profile.append(f"Description: {workspace.description}")
            if workspace.mode:
                workspace_profile.append(f"Mode: {workspace.mode}")

        active_intents_summary = []
        if profile_id and self.store:
            try:
                from ...models.mindscape import IntentStatus
                active_intents = self.store.list_intents(
                    profile_id=profile_id,
                    status=IntentStatus.ACTIVE
                )
                if active_intents:
                    for intent in active_intents[:5]:
                        intent_summary = f"- {intent.title}"
                        if intent.description:
                            intent_summary += f": {intent.description[:100]}"
                        active_intents_summary.append(intent_summary)
            except Exception as e:
                logger.warning(f"Failed to get active intents: {e}")

        if workspace_profile or active_intents_summary:
            context_parts.append("## Workspace Profile")
            if workspace_profile:
                context_parts.extend(workspace_profile)
            if active_intents_summary:
                context_parts.append("\nKey Long-term Intents:")
                context_parts.extend(active_intents_summary)

        # 2. Recent Conversation (compressed with summary support)
        # Use token budget to determine how much conversation to include
        conversation_budget = int(target_tokens * 0.4)
        max_events = self.preset["MAX_EVENTS_FOR_QUERY"]
        max_messages = self.preset["MAX_HISTORY_MESSAGES"]
        max_chars = self.preset["MAX_MESSAGE_CHARS"]

        try:
            if self.store:
                conversation_context, summary_context = await self._get_conversation_history_with_summary(
                    workspace_id=workspace_id,
                    max_events=max_events,
                    max_messages=max_messages,
                    max_chars=max_chars
                )

                if summary_context:
                    context_parts.append("\n## Conversation Summary (Earlier Context):")
                    context_parts.append(summary_context)

                if conversation_context:
                    context_parts.append("\n## Recent Conversation (last N turns, compressed):")
                    messages_to_include = []
                    current_tokens = 0
                    for msg in reversed(conversation_context):
                        msg_tokens = self.estimate_token_count(msg, model_name=None)
                        if current_tokens + msg_tokens <= conversation_budget:
                            messages_to_include.insert(0, msg)
                            current_tokens += msg_tokens
                        else:
                            break
                    context_parts.extend(messages_to_include)
                    logger.info(f"Included {len(messages_to_include)} recent messages ({current_tokens} tokens) for planning context")
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}", exc_info=True)

        active_packs_info = []
        if self.store:
            try:
                from ..stores.tasks_store import TasksStore
                from ...models.workspace import TaskStatus
                tasks_store = TasksStore(self.store.db_path)

                running_tasks = tasks_store.list_running_tasks(workspace_id)
                pending_tasks = tasks_store.list_pending_tasks(workspace_id)

                packs_state = {}
                for task in (running_tasks + pending_tasks)[:10]:
                    pack_id = task.pack_id if hasattr(task, 'pack_id') else None
                    if pack_id:
                        if pack_id not in packs_state:
                            packs_state[pack_id] = []
                        status = task.status.value if hasattr(task.status, 'value') else str(task.status)
                        packs_state[pack_id].append(status)

                if packs_state:
                    context_parts.append("\n## Active Packs & Their State:")
                    for pack_id, states in list(packs_state.items())[:5]:
                        state_summary = ", ".join(set(states))
                        active_packs_info.append(f"- {pack_id}: {state_summary}")
                    context_parts.extend(active_packs_info)
            except Exception as e:
                logger.warning(f"Failed to get active packs state: {e}")

        timeline_summary = []
        try:
            if self.timeline_items_store:
                recent_timeline_items = self.timeline_items_store.list_timeline_items_by_workspace(
                    workspace_id=workspace_id,
                    limit=10
                )
                if recent_timeline_items:
                    for item in recent_timeline_items[:5]:
                        item_type = item.type.value if hasattr(item.type, 'value') else str(item.type)
                        item_info = f"- {item_type}: {item.title}"
                        if item.summary:
                            item_info += f" - {item.summary[:100]}"
                        timeline_summary.append(item_info)
                    if timeline_summary:
                        context_parts.append("\n## Recent Timeline Activity (top 5):")
                        context_parts.extend(timeline_summary)
        except Exception as e:
            logger.warning(f"Failed to get timeline context: {e}")

        planning_context = "\n".join(context_parts) if context_parts else ""

        final_tokens = self.estimate_token_count(planning_context, model_name=None)
        logger.info(f"Built planning context: {final_tokens} tokens (target: {target_tokens})")

        return planning_context

    def build_enhanced_prompt(
        self,
        message: str,
        context: str
    ) -> str:
        """
        Build enhanced prompt with context

        Args:
            message: User message
            context: Context string from build_qa_context

        Returns:
            Enhanced prompt with context injected
        """
        system_instructions = """You are an intelligent workspace assistant with complete awareness of the workspace context. This workspace is served by a single AI assistant that can play multiple professional roles, equivalent to multiple AI teams collaborating. Each capability pack represents a specialized AI team with distinct expertise.

CRITICAL: You have access to complete workspace context including:
- Workspace goals and objectives (from Active Intents section)
- Current tasks and progress (from Current Tasks section)
- Recent activity timeline (from Recent Timeline Activity section)
- Conversation history (from Recent Conversation section)
- Available capabilities (from Available Capability Packs section)

IMPORTANT GUIDELINES:
1. **Use the complete context**: Reference specific intents, tasks, and timeline items when answering
2. **Avoid repetition**: Do NOT repeat the same information if it's already in the context
3. **Be specific**: If context mentions specific goals or tasks, reference them directly
4. **Stay coherent**: Build upon previous conversations and context, don't start from scratch
5. **Acknowledge progress**: If tasks or intents are mentioned, acknowledge their current status

When explaining available capabilities:
- Describe capability packs as specialized AI teams or professional roles
- Explain how different teams can collaborate on complex tasks
- Reference specific active intents or tasks when suggesting capabilities
- Use natural, user-friendly language to explain the multi-AI team concept

Answer questions based on the complete workspace context. Be specific, practical, and avoid repeating information that's already provided in the context."""

        if not context:
            return f"""{system_instructions}

User question: {message}

Please provide a helpful answer."""

        return f"""{system_instructions}

User question: {message}

Context from this workspace:
{context}

Please answer the user's question based on the context above. If the context includes available capability packs, explain them as specialized AI teams that can collaborate. If the context is relevant, use it to provide a specific, actionable answer. If not, provide a helpful general answer."""
