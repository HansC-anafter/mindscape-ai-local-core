"""
Context Builder Service

Main facade for building context for LLM prompts from workspace data:
- Recent file analysis results
- Timeline items (pack execution results)
- Recent conversation history
- Multi-scope memory (RAG)
"""

import logging
from typing import Dict, Any, List, Optional, Tuple

from backend.app.services.model_context_presets import get_context_preset
from backend.app.services.pack_info_collector import PackInfoCollector
from backend.app.shared.llm_provider_helper import get_llm_provider_from_settings

from .token_estimator import TokenEstimator
from .summary_policy import SummaryPolicy
from .memory_retriever import MemoryRetriever
from .conversation_history import ConversationHistoryManager
from .side_chain_handler import SideChainHandler

logger = logging.getLogger(__name__)


class ContextBuilder:
    """Build context for LLM prompts from workspace data"""

    def __init__(
        self, store=None, timeline_items_store=None, model_name: Optional[str] = None
    ):
        """
        Initialize ContextBuilder

        Args:
            store: MindscapeStore instance
            timeline_items_store: TimelineItemsStore instance
            model_name: Model name for context preset selection (required)
                       Must be explicitly provided from SystemSettingsStore
        """
        self.store = store
        self.timeline_items_store = timeline_items_store

        # Model name must be explicitly provided - no fallback allowed
        if not model_name or model_name.strip() == "":
            raise ValueError(
                "model_name is required for ContextBuilder. "
                "Please get the model name from SystemSettingsStore and pass it explicitly."
            )

        self.model_name = model_name
        self.preset = get_context_preset(model_name)

        # Initialize sub-components
        self.token_estimator = TokenEstimator(model_name=model_name)
        self.summary_policy = SummaryPolicy(store=store, model_name=model_name)
        self.memory_retriever = MemoryRetriever(store=store)
        self.conversation_history_manager = ConversationHistoryManager(
            store=store, summary_policy=self.summary_policy
        )
        self.side_chain_handler = SideChainHandler(
            store=store, timeline_items_store=timeline_items_store
        )

        logger.info(
            f"ContextBuilder initialized with model: {model_name or 'default'}, "
            f"preset: MAX_EVENTS={self.preset['MAX_EVENTS_FOR_QUERY']}, "
            f"MAX_MESSAGES={self.preset['MAX_HISTORY_MESSAGES']}, "
            f"MAX_CHARS={self.preset['MAX_MESSAGE_CHARS']}"
        )

    async def build_qa_context(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        project_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        hours: int = 24,
        side_chain_mode: str = "off",
    ) -> str:
        """
        Build context string for QA mode LLM prompts

        Args:
            workspace_id: Workspace ID
            message: User message
            profile_id: Optional profile ID for retrieving intents
            workspace: Optional workspace object for metadata
            project_id: Optional project ID for project-specific context
            thread_id: Optional thread ID for thread-specific references (P0-9)
            hours: Hours to look back for context (default 24)
            side_chain_mode: Side-chain policy ("off", "auto", "force")

        Returns:
            Context string to inject into LLM prompt
        """
        context_parts = []

        # Layered memory system
        context_parts.extend(
            await self._build_layered_memory_context(
                workspace_id, profile_id, project_id
            )
        )

        # Workspace metadata
        context_parts.extend(
            self._build_workspace_metadata_context(workspace, workspace_id)
        )

        # Active intents
        context_parts.extend(await self._build_active_intents_context(profile_id))

        # Current tasks
        context_parts.extend(
            await self._build_current_tasks_context(workspace_id, thread_id)
        )

        # Recent files
        context_parts.extend(await self._build_recent_files_context(workspace_id))

        # Timeline items
        context_parts.extend(
            await self._build_timeline_context(workspace_id, thread_id)
        )

        # Thread references
        context_parts.extend(
            await self._build_thread_references_context(workspace_id, thread_id)
        )

        # Conversation history with summary
        thread_context_count = 0
        try:
            if self.store:
                max_events = self.preset["MAX_EVENTS_FOR_QUERY"]
                max_messages = self.preset["MAX_HISTORY_MESSAGES"]
                max_chars = self.preset["MAX_MESSAGE_CHARS"]

                conversation_context, summary_context = (
                    await self.conversation_history_manager.get_conversation_history_with_summary(
                        workspace_id=workspace_id,
                        max_events=max_events,
                        max_messages=max_messages,
                        max_chars=max_chars,
                        thread_id=thread_id,
                    )
                )

                if summary_context:
                    context_parts.append("\n## Conversation Summary (Earlier Context):")
                    context_parts.append(summary_context)
                    logger.info("Injected conversation summary into QA context")

                if conversation_context:
                    context_parts.append("\n## Recent Conversation:")
                    context_parts.extend(conversation_context)
                    thread_context_count = len(conversation_context)
                    logger.info(
                        f"Injected {len(conversation_context)} conversation messages into QA context"
                    )
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}", exc_info=True)

        # Side chain context
        try:
            if self.side_chain_handler.should_include_side_chain(
                side_chain_mode=side_chain_mode,
                thread_id=thread_id,
                message=message,
                thread_context_count=thread_context_count,
            ):
                side_chain_parts = (
                    self.side_chain_handler.build_workspace_side_chain_context(
                        workspace_id=workspace_id
                    )
                )
                if side_chain_parts:
                    context_parts.extend(side_chain_parts)
                    logger.info("Injected workspace side-chain into QA context")
        except Exception as e:
            logger.warning(f"Failed to build workspace side-chain context: {e}")

        # Long-term memory (RAG)
        try:
            long_term_memory = await self.memory_retriever.get_long_term_memory_context(
                workspace_id=workspace_id, message=message, profile_id=profile_id
            )
            if long_term_memory:
                context_parts.append("\n## Long-term Knowledge:")
                context_parts.append(long_term_memory)
                logger.info("Injected long-term memory context into QA context")
        except Exception as e:
            logger.debug(f"Failed to get long-term memory context: {e}")

        return "\n".join(context_parts) if context_parts else ""

    async def _build_layered_memory_context(
        self, workspace_id: str, profile_id: Optional[str], project_id: Optional[str]
    ) -> List[str]:
        """Build layered memory context (workspace core, project, member)"""
        context_parts = []
        try:
            from backend.app.services.memory.workspace_core_memory import (
                WorkspaceCoreMemoryService,
            )
            from backend.app.services.memory.project_memory import ProjectMemoryService
            from backend.app.services.memory.member_profile_memory import (
                MemberProfileMemoryService,
            )

            workspace_memory_service = WorkspaceCoreMemoryService(self.store)
            workspace_core_memory = await workspace_memory_service.get_core_memory(
                workspace_id
            )
            core_memory_context = workspace_memory_service.format_for_context(
                workspace_core_memory
            )
            if core_memory_context:
                context_parts.append("\n## Workspace Core Memory:")
                context_parts.append(core_memory_context)
                logger.info("Injected workspace core memory into QA context")

            if project_id:
                project_memory_service = ProjectMemoryService(self.store)
                try:
                    project_memory = await project_memory_service.get_project_memory(
                        project_id, workspace_id
                    )
                    project_memory_context = project_memory_service.format_for_context(
                        project_memory
                    )
                    if project_memory_context:
                        context_parts.append("\n## Project Memory:")
                        context_parts.append(project_memory_context)
                        logger.info(f"Injected project memory for project {project_id}")
                except Exception as e:
                    logger.warning(f"Failed to load project memory: {e}")

            if profile_id:
                member_memory_service = MemberProfileMemoryService(self.store)
                try:
                    member_memory = await member_memory_service.get_member_memory(
                        profile_id, workspace_id
                    )
                    member_memory_context = member_memory_service.format_for_context(
                        member_memory, include_experiences=True
                    )
                    if member_memory_context:
                        context_parts.append("\n## Member Profile:")
                        context_parts.append(member_memory_context)
                        logger.info(
                            f"Injected member profile memory for user {profile_id}"
                        )
                except Exception as e:
                    logger.warning(f"Failed to load member memory: {e}")
        except Exception as e:
            logger.warning(f"Failed to load layered memory: {e}")

        return context_parts

    def _build_workspace_metadata_context(
        self, workspace: Any, workspace_id: str
    ) -> List[str]:
        """Build workspace metadata context"""
        context_parts = []
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
                logger.info(
                    f"Injected workspace metadata: {workspace.title or workspace_id}"
                )
        return context_parts

    async def _build_active_intents_context(
        self, profile_id: Optional[str]
    ) -> List[str]:
        """Build active intents context"""
        context_parts = []
        if profile_id and self.store:
            try:
                from backend.app.models.mindscape import IntentStatus

                active_intents = self.store.list_intents(
                    profile_id=profile_id, status=IntentStatus.ACTIVE
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
                            intent_info += (
                                f" [Progress: {intent.progress_percentage:.0f}%]"
                            )
                        context_parts.append(intent_info)
                    logger.info(f"Injected {len(active_intents)} active intents")
            except Exception as e:
                logger.warning(f"Failed to get active intents: {e}")
        return context_parts

    async def _build_current_tasks_context(
        self, workspace_id: str, thread_id: Optional[str]
    ) -> List[str]:
        """Build current tasks context"""
        context_parts = []
        if self.store:
            try:
                from backend.app.services.stores.tasks_store import TasksStore
                from backend.app.models.workspace import TaskStatus

                tasks_store = TasksStore(self.store.db_path)

                if thread_id:
                    pending_tasks = tasks_store.list_pending_tasks_by_thread(
                        workspace_id, thread_id
                    )
                    running_tasks = tasks_store.list_running_tasks_by_thread(
                        workspace_id, thread_id
                    )
                else:
                    pending_tasks = tasks_store.list_pending_tasks(workspace_id)
                    running_tasks = tasks_store.list_running_tasks(workspace_id)

                if pending_tasks or running_tasks:
                    context_parts.append("\n## Current Tasks:")

                    tasks_by_intent = {}
                    unlinked_tasks = []

                    for task in (running_tasks + pending_tasks)[:10]:
                        intent_title = None
                        if hasattr(task, "intent_id") and task.intent_id:
                            try:
                                intent = self.store.get_intent(task.intent_id)
                                if intent:
                                    intent_title = intent.title
                            except Exception:
                                pass

                        task_status = (
                            task.status.value
                            if hasattr(task.status, "value")
                            else str(task.status)
                        )
                        task_info = f"- {task.pack_id} ({task_status})"
                        if task.task_type:
                            task_info += f": {task.task_type}"
                        if task.params and isinstance(task.params, dict):
                            source = task.params.get("source", "")
                            if source:
                                task_info += f" [Source: {source}]"

                        if intent_title:
                            if intent_title not in tasks_by_intent:
                                tasks_by_intent[intent_title] = []
                            tasks_by_intent[intent_title].append(task_info)
                        else:
                            unlinked_tasks.append(task_info)

                    for intent_title, task_list in tasks_by_intent.items():
                        context_parts.append(f"\n  Under Intent: {intent_title}")
                        context_parts.extend([f"    {task}" for task in task_list])

                    if unlinked_tasks:
                        context_parts.extend(unlinked_tasks)

                    logger.info(
                        f"Injected {len(pending_tasks) + len(running_tasks)} current tasks"
                    )
            except Exception as e:
                logger.warning(f"Failed to get current tasks: {e}")
        return context_parts

    async def _build_recent_files_context(self, workspace_id: str) -> List[str]:
        """Build recent files context from file analysis events"""
        context_parts = []
        try:
            if self.store:
                recent_events = self.store.get_events_by_workspace(
                    workspace_id=workspace_id, limit=50
                )
                file_events = []
                for event in recent_events:
                    if (
                        hasattr(event, "event_type")
                        and event.event_type.value == "file_analysis"
                    ):
                        payload = (
                            event.payload if isinstance(event.payload, dict) else {}
                        )
                        metadata = (
                            event.metadata if isinstance(event.metadata, dict) else {}
                        )
                        file_analysis = metadata.get("file_analysis", {})
                        if file_analysis:
                            file_events.append(
                                {
                                    "name": payload.get("filename", "Unknown"),
                                    "analysis_summary": file_analysis.get(
                                        "analysis", {}
                                    ).get("summary", ""),
                                    "themes": file_analysis.get("analysis", {}).get(
                                        "themes", []
                                    ),
                                }
                            )

                if file_events:
                    context_parts.append("\n## Recent Files:")
                    for file_ctx in file_events[:3]:
                        file_info = f"- {file_ctx.get('name', 'Unknown')}"
                        if file_ctx.get("analysis_summary"):
                            file_info += f" ({file_ctx.get('analysis_summary')[:100]})"
                        if file_ctx.get("themes"):
                            file_info += f"\n  Themes: {', '.join(file_ctx.get('themes', [])[:5])}"
                        context_parts.append(file_info)
        except Exception as e:
            logger.warning(f"Failed to get file context: {e}")
        return context_parts

    async def _build_timeline_context(
        self, workspace_id: str, thread_id: Optional[str]
    ) -> List[str]:
        """Build timeline context"""
        context_parts = []
        try:
            if self.timeline_items_store:
                if thread_id:
                    recent_timeline_items = (
                        self.timeline_items_store.list_timeline_items_by_thread(
                            workspace_id=workspace_id, thread_id=thread_id, limit=30
                        )
                    )
                else:
                    recent_timeline_items = (
                        self.timeline_items_store.list_timeline_items_by_workspace(
                            workspace_id=workspace_id, limit=30
                        )
                    )
                if recent_timeline_items:
                    context_parts.append("\n## Recent Timeline Activity:")
                    for item in recent_timeline_items[:30]:
                        item_type = (
                            item.type.value
                            if hasattr(item.type, "value")
                            else str(item.type)
                        )
                        item_info = f"- {item_type}: {item.title}"
                        if item.summary:
                            item_info += f" - {item.summary[:200]}"
                        context_parts.append(item_info)
                    logger.info(f"Injected {len(recent_timeline_items)} timeline items")
        except Exception as e:
            logger.error(f"Failed to get timeline context: {e}", exc_info=True)
        return context_parts

    async def _build_thread_references_context(
        self, workspace_id: str, thread_id: Optional[str]
    ) -> List[str]:
        """Build thread references context"""
        context_parts = []
        try:
            if thread_id and self.store:
                thread_references = self.store.thread_references.get_by_thread(
                    workspace_id=workspace_id, thread_id=thread_id, limit=20
                )
                if thread_references:
                    ref_lines = []
                    ref_tokens = 0
                    max_ref_tokens = 500

                    for ref in thread_references:
                        ref_info = f"- [{ref.title}]({ref.uri})"
                        if ref.source_type:
                            ref_info += f" ({ref.source_type})"
                        snippet_text = ""
                        if ref.snippet:
                            snippet_text = f": {ref.snippet[:200]}"
                        if ref.reason:
                            snippet_text += f" [Reason: {ref.reason}]"

                        ref_line = ref_info + snippet_text
                        line_tokens = (
                            self.estimate_token_count(ref_line, self.model_name)
                            or len(ref_line.split()) * 2
                        )

                        if ref_tokens + line_tokens > max_ref_tokens:
                            logger.info(
                                f"Thread references token budget reached ({ref_tokens}/{max_ref_tokens})"
                            )
                            break

                        ref_lines.append(ref_line)
                        ref_tokens += line_tokens

                    if ref_lines:
                        context_parts.append(
                            "\n## Thread References (Pinned Resources):"
                        )
                        context_parts.extend(ref_lines)
                        logger.info(f"Injected {len(ref_lines)} thread references")
        except Exception as e:
            logger.warning(f"Failed to get thread references context: {e}")
        return context_parts

    def estimate_token_count(self, text: str, model_name: Optional[str] = None) -> int:
        """Delegate token counting to TokenEstimator"""
        return self.token_estimator.estimate(text, model_name)

    async def should_summarize(
        self,
        workspace_id: str,
        conversation_context: List[str],
        recent_events: List[Any],
    ) -> Tuple[bool, str]:
        """Delegate to SummaryPolicy"""
        return await self.summary_policy.should_summarize(
            workspace_id, conversation_context, recent_events
        )

    async def _get_conversation_history_with_summary(
        self,
        workspace_id: str,
        max_events: int,
        max_messages: int,
        max_chars: int,
        thread_id: Optional[str] = None,
    ) -> Tuple[List[str], Optional[str]]:
        """Delegate to ConversationHistoryManager"""
        return await self.conversation_history_manager.get_conversation_history_with_summary(
            workspace_id, max_events, max_messages, max_chars, thread_id
        )

    def _should_include_side_chain(
        self,
        side_chain_mode: str,
        thread_id: Optional[str],
        message: Optional[str],
        thread_context_count: int,
    ) -> bool:
        """Delegate to SideChainHandler"""
        return self.side_chain_handler.should_include_side_chain(
            side_chain_mode, thread_id, message, thread_context_count
        )

    def _build_workspace_side_chain_context(
        self, workspace_id: str, task_limit: int = 5, timeline_limit: int = 5
    ) -> List[str]:
        """Delegate to SideChainHandler"""
        return self.side_chain_handler.build_workspace_side_chain_context(
            workspace_id, task_limit, timeline_limit
        )

    async def _get_multi_scope_memory(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        intent_id: Optional[str] = None,
    ) -> Optional[str]:
        """Delegate to MemoryRetriever"""
        return await self.memory_retriever.get_multi_scope_memory(
            workspace_id, message, profile_id, intent_id
        )

    async def _get_long_term_memory_context(
        self, workspace_id: str, message: str, profile_id: Optional[str] = None
    ) -> Optional[str]:
        """Delegate to MemoryRetriever"""
        return await self.memory_retriever.get_long_term_memory_context(
            workspace_id, message, profile_id
        )

    async def _generate_and_store_summary(
        self,
        workspace_id: str,
        messages_to_summarize: List[str],
        profile_id: Optional[str] = None,
        summary_type: str = "HISTORY_SUMMARY",
    ):
        """Delegate to SummaryPolicy"""
        return await self.summary_policy.generate_and_store_summary(
            workspace_id, messages_to_summarize, profile_id, summary_type
        )

    def _calculate_capacity_score(self, conversation_context: List[str]) -> float:
        """Delegate to SummaryPolicy"""
        return self.summary_policy._calculate_capacity_score(conversation_context)

    async def _detect_episode_boundary(
        self, workspace_id: str, recent_events: List[Any]
    ) -> Tuple[float, str]:
        """Delegate to SummaryPolicy"""
        return await self.summary_policy._detect_episode_boundary(
            workspace_id, recent_events
        )

    async def _calculate_salience_score(
        self, conversation_context: List[str], recent_events: List[Any]
    ) -> float:
        """Delegate to SummaryPolicy"""
        return await self.summary_policy._calculate_salience_score(
            conversation_context, recent_events
        )

    async def build_qa_context_with_token_count(
        self,
        workspace_id: str,
        message: str,
        profile_id: Optional[str] = None,
        workspace: Optional[Any] = None,
        thread_id: Optional[str] = None,
        hours: int = 24,
        side_chain_mode: str = "off",
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
            thread_id=thread_id,
            hours=hours,
            side_chain_mode=side_chain_mode,
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
        mode: str = "planning",
        thread_id: Optional[str] = None,
        side_chain_mode: str = "off",
    ) -> str:
        """
        Build structured context specifically for planning tasks

        Args:
            workspace_id: Workspace ID
            message: User message
            profile_id: Optional profile ID for retrieving intents
            workspace: Optional workspace object for metadata
            target_tokens: Target token budget for the context
            mode: Context mode ("planning" or "qa")
            thread_id: Optional thread ID for thread-scoped context
            side_chain_mode: Side-chain policy ("off", "auto", "force")

        Returns:
            Structured context string optimized for planning tasks
        """
        context_parts = []

        if target_tokens is None:
            model_max_tokens = 16385
            if hasattr(self, "model_name") and self.model_name:
                from backend.app.services.model_context_presets import (
                    get_context_preset,
                )

                try:
                    model_preset = get_context_preset(self.model_name)
                    model_max_tokens = model_preset.get(
                        "MAX_CONTEXT_TOKENS", model_max_tokens
                    )
                except Exception:
                    pass
            target_tokens = int(model_max_tokens * 0.6)

        logger.info(
            f"Building planning context with target_tokens={target_tokens}, mode={mode}"
        )

        # Workspace profile
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
                from backend.app.models.mindscape import IntentStatus

                active_intents = self.store.list_intents(
                    profile_id=profile_id, status=IntentStatus.ACTIVE
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

        # Conversation history with budget
        conversation_budget = int(target_tokens * 0.4)
        max_events = self.preset["MAX_EVENTS_FOR_QUERY"]
        max_messages = self.preset["MAX_HISTORY_MESSAGES"]
        max_chars = self.preset["MAX_MESSAGE_CHARS"]

        thread_context_count = 0
        try:
            if self.store:
                conversation_context, summary_context = (
                    await self.conversation_history_manager.get_conversation_history_with_summary(
                        workspace_id=workspace_id,
                        max_events=max_events,
                        max_messages=max_messages,
                        max_chars=max_chars,
                        thread_id=thread_id,
                    )
                )

                if summary_context:
                    context_parts.append("\n## Conversation Summary (Earlier Context):")
                    context_parts.append(summary_context)

                if conversation_context:
                    context_parts.append(
                        "\n## Recent Conversation (last N turns, compressed):"
                    )
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
                    thread_context_count = len(messages_to_include)
                    logger.info(
                        f"Included {len(messages_to_include)} messages ({current_tokens} tokens) for planning"
                    )
        except Exception as e:
            logger.error(f"Failed to get conversation context: {e}", exc_info=True)

        # Active packs
        active_packs_info = []
        if self.store:
            try:
                from backend.app.services.stores.tasks_store import TasksStore
                from backend.app.models.workspace import TaskStatus

                tasks_store = TasksStore(self.store.db_path)

                if thread_id:
                    running_tasks = tasks_store.list_running_tasks_by_thread(
                        workspace_id, thread_id
                    )
                    pending_tasks = tasks_store.list_pending_tasks_by_thread(
                        workspace_id, thread_id
                    )
                else:
                    running_tasks = tasks_store.list_running_tasks(workspace_id)
                    pending_tasks = tasks_store.list_pending_tasks(workspace_id)

                packs_state = {}
                for task in (running_tasks + pending_tasks)[:10]:
                    pack_id = task.pack_id if hasattr(task, "pack_id") else None
                    if pack_id:
                        if pack_id not in packs_state:
                            packs_state[pack_id] = []
                        status = (
                            task.status.value
                            if hasattr(task.status, "value")
                            else str(task.status)
                        )
                        packs_state[pack_id].append(status)

                if packs_state:
                    context_parts.append("\n## Active Packs & Their State:")
                    for pack_id, states in list(packs_state.items())[:5]:
                        state_summary = ", ".join(set(states))
                        active_packs_info.append(f"- {pack_id}: {state_summary}")
                    context_parts.extend(active_packs_info)
            except Exception as e:
                logger.warning(f"Failed to get active packs state: {e}")

        # Timeline
        timeline_summary = []
        try:
            if self.timeline_items_store:
                if thread_id:
                    recent_timeline_items = (
                        self.timeline_items_store.list_timeline_items_by_thread(
                            workspace_id=workspace_id, thread_id=thread_id, limit=10
                        )
                    )
                else:
                    recent_timeline_items = (
                        self.timeline_items_store.list_timeline_items_by_workspace(
                            workspace_id=workspace_id, limit=10
                        )
                    )
                if recent_timeline_items:
                    for item in recent_timeline_items[:5]:
                        item_type = (
                            item.type.value
                            if hasattr(item.type, "value")
                            else str(item.type)
                        )
                        item_info = f"- {item_type}: {item.title}"
                        if item.summary:
                            item_info += f" - {item.summary[:100]}"
                        timeline_summary.append(item_info)
                    if timeline_summary:
                        context_parts.append("\n## Recent Timeline Activity (top 5):")
                        context_parts.extend(timeline_summary)
        except Exception as e:
            logger.warning(f"Failed to get timeline context: {e}")

        # Side chain
        try:
            if self.side_chain_handler.should_include_side_chain(
                side_chain_mode=side_chain_mode,
                thread_id=thread_id,
                message=message,
                thread_context_count=thread_context_count,
            ):
                side_chain_parts = (
                    self.side_chain_handler.build_workspace_side_chain_context(
                        workspace_id=workspace_id
                    )
                )
                if side_chain_parts:
                    context_parts.extend(side_chain_parts)
                    logger.info("Injected workspace side-chain into planning context")
        except Exception as e:
            logger.warning(
                f"Failed to build workspace side-chain for planning context: {e}"
            )

        planning_context = "\n".join(context_parts) if context_parts else ""

        final_tokens = self.estimate_token_count(planning_context, model_name=None)
        logger.info(
            f"Built planning context: {final_tokens} tokens (target: {target_tokens})"
        )

        return planning_context

    def build_enhanced_prompt(self, message: str, context: str) -> str:
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
