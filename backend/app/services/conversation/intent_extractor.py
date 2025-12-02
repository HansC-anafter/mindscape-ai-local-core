"""
Intent Extractor Service

Handles LLM-based intent extraction from user messages with context.
Creates TimelineItem (type=INTENT_SEEDS) for extracted intents/themes.
"""

import logging
import os
import sys
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from ...models.workspace import TimelineItem, TimelineItemType
from ...models.mindscape import IntentTag, IntentTagStatus, IntentSource
from ...services.mindscape_store import MindscapeStore
from ...services.stores.timeline_items_store import TimelineItemsStore
from ...services.stores.intent_tags_store import IntentTagsStore
from ...services.i18n_service import get_i18n_service
from ...core.execution_context import ExecutionContext
from ...core.ports.intent_registry_port import IntentRegistryPort
from backend.app.services.conversation.context_builder import ContextBuilder
from backend.app.services.conversation.pack_suggester import PackSuggester
from backend.app.services.pack_info_collector import PackInfoCollector

logger = logging.getLogger(__name__)


class IntentExtractor:
    """
    Intent Extractor - extracts intents/themes using IntentRegistryPort and creates timeline items

    Responsibilities:
    - Build context from recent files and timeline items
    - Extract intents/themes using IntentRegistryPort
    - Create TimelineItem (type=INTENT_SEEDS) for results
    - Update event metadata with extracted intents/themes
    """

    def __init__(
        self,
        store: MindscapeStore,
        timeline_items_store: TimelineItemsStore,
        intent_registry: IntentRegistryPort,
        default_locale: str = "en"
    ):
        """
        Initialize Intent Extractor

        Args:
            store: MindscapeStore instance
            timeline_items_store: TimelineItemsStore instance
            intent_registry: IntentRegistryPort instance
            default_locale: Default locale for i18n
        """
        self.store = store
        self.timeline_items_store = timeline_items_store
        self.default_locale = default_locale
        self.i18n = get_i18n_service(default_locale=default_locale)

        self.intent_registry = intent_registry
        self.intent_tags_store = IntentTagsStore(db_path=store.db_path)
        self.context_builder = ContextBuilder(
            store=store,
            timeline_items_store=timeline_items_store
        )
        self.pack_suggester = PackSuggester()
        self.pack_info_collector = PackInfoCollector(db_path=store.db_path)

    async def extract_and_create_timeline_item(
        self,
        ctx: ExecutionContext,
        message: str,
        message_id: str,
        locale: Optional[str] = None
    ) -> Optional[TimelineItem]:
        """
        Extract intents/themes from message and create timeline item

        Args:
            ctx: Execution context
            message: User message text
            message_id: Message/event ID
            locale: Target locale (optional)

        Returns:
            Created TimelineItem or None if extraction failed or disabled
        """
        # Check if LLM extractor is enabled
        enable_llm_extractor = os.getenv("ENABLE_LLM_INTENT_EXTRACTOR", "true").lower() == "true"
        if not enable_llm_extractor:
            logger.info("LLM intent extractor is disabled via ENABLE_LLM_INTENT_EXTRACTOR")
            print("LLM intent extractor is disabled via ENABLE_LLM_INTENT_EXTRACTOR", file=sys.stderr)
            return None

        try:
            logger.info(f"Intent extractor: Starting extraction for workspace {ctx.workspace_id}, message: {message[:100]}...")
            print(f"Intent extractor: Starting extraction for workspace {ctx.workspace_id}, message: {message[:100]}...", file=sys.stderr)

            # Build context from recent files and timeline items
            context_str = ""
            try:
                context_str = await self.context_builder.build_qa_context(
                    workspace_id=ctx.workspace_id,
                    message=message,
                    hours=24
                )
                logger.info(f"Intent extractor: Built context ({len(context_str)} chars)")
            except Exception as ctx_err:
                logger.warning(f"Intent extractor: failed to build context: {ctx_err}", exc_info=True)

            # Extract intents/themes using IntentRegistryPort
            logger.info(f"Intent extractor: Calling intent registry with message and context")
            resolution_result = await self.intent_registry.resolve_intent(
                user_input=message,
                ctx=ctx,
                context=context_str,
                locale=locale or self.default_locale
            )
            logger.info(f"Intent extractor: Registry returned: {resolution_result.intents} intents, {resolution_result.themes} themes")
            print(f"Intent extractor: Registry returned: {len(resolution_result.intents)} intents, {len(resolution_result.themes)} themes", file=sys.stderr)

            intents_list = resolution_result.intents
            themes_list = resolution_result.themes

            logger.info(f"Intent extractor: Parsed {len(intents_list)} intents, {len(themes_list)} themes")
            print(f"Intent extractor: Parsed {len(intents_list)} intents, {len(themes_list)} themes", file=sys.stderr)

            # Create candidate IntentTags for extracted intents
            llm_confidence = resolution_result.confidence or 0.0
            intent_tag_ids = []
            for intent_item in intents_list[:5]:
                try:
                    if isinstance(intent_item, dict):
                        intent_label = intent_item.get("title") or intent_item.get("text") or str(intent_item)
                        intent_confidence = intent_item.get("confidence", llm_confidence)
                    else:
                        intent_label = str(intent_item)
                        intent_confidence = llm_confidence

                    if intent_label and len(intent_label.strip()) > 0:
                        candidate_tag = IntentTag(
                            id=str(uuid.uuid4()),
                            workspace_id=ctx.workspace_id,
                            profile_id=ctx.actor_id,
                            label=intent_label.strip(),
                            confidence=float(intent_confidence) if intent_confidence else None,
                            status=IntentTagStatus.CANDIDATE,
                            source=IntentSource.LLM,
                            execution_id=None,
                            playbook_code=None,
                            message_id=message_id,
                            metadata={
                                "extraction_source": "intent_extractor",
                                "llm_analysis": resolution_result.llm_analysis or {}
                            },
                            created_at=datetime.utcnow(),
                            updated_at=datetime.utcnow(),
                            confirmed_at=None,
                            rejected_at=None
                        )
                        self.intent_tags_store.create_intent_tag(candidate_tag)
                        intent_tag_ids.append(candidate_tag.id)
                        logger.info(f"Created candidate IntentTag {candidate_tag.id}: {intent_label[:50]}")
                except Exception as e:
                    logger.warning(f"Failed to create candidate IntentTag: {e}")

            # Create TimelineItem if we got results
            if not intents_list and not themes_list:
                logger.info("Intent extractor: No intents or themes extracted, returning None")
                print(f"Intent extractor: No intents or themes extracted, returning None", file=sys.stderr)
                return None

            # Format summary from intents/themes
            summary_parts = []
            if intents_list:
                intent_titles = [
                    i.get("title", "") if isinstance(i, dict) else str(i)
                    for i in intents_list[:3]
                ]
                summary_parts.append("Intents: " + ", ".join(intent_titles))
            if themes_list:
                theme_strs = [str(t) for t in themes_list[:3]]
                summary_parts.append("Themes: " + ", ".join(theme_strs))

            summary = " | ".join(summary_parts) if summary_parts else "LLM extracted intents and themes"

            # Check if should auto-execute based on workspace config
            # Similar to task auto-execution mechanism
            from ...services.stores.workspaces_store import WorkspacesStore
            workspaces_store = WorkspacesStore(self.store.db_path)
            workspace = workspaces_store.get_workspace(ctx.workspace_id)

            auto_exec_config = workspace.playbook_auto_execution_config if workspace else None
            should_auto_execute = False

            # Check for intent extraction auto-execution config
            # Use "intent_extraction" as the playbook_code for intent extraction
            if auto_exec_config and "intent_extraction" in auto_exec_config:
                intent_config = auto_exec_config["intent_extraction"]
                confidence_threshold = intent_config.get('confidence_threshold', 0.8)
                auto_execute_enabled = intent_config.get('auto_execute', False)

                # Get confidence from resolution result
                llm_confidence = resolution_result.confidence or 0.0
                # Default confidence if not provided (assume high confidence for intent extraction)
                if llm_confidence == 0.0:
                    llm_confidence = 0.9

                if auto_execute_enabled and llm_confidence >= confidence_threshold:
                    should_auto_execute = True
                    logger.info(f"IntentExtractor: Intent extraction meets auto-exec threshold (confidence={llm_confidence:.2f} >= {confidence_threshold:.2f})")
                else:
                    logger.info(f"IntentExtractor: Intent extraction does not meet auto-exec threshold (confidence={llm_confidence:.2f} < {confidence_threshold:.2f})")

            if should_auto_execute:
                # Auto-execute: Candidate intents are already created as IntentTags above
                # Only confirmed intents will be written to long-term memory (IntentCard)
                # This change ensures candidate intents are not automatically written to long-term memory
                from ...models.workspace import Task, TaskStatus
                from ...services.stores.tasks_store import TasksStore

                tasks_store = TasksStore(self.store.db_path)

                # Count candidate IntentTags created (not IntentCards)
                intents_created = len(intent_tag_ids)

                # Create task for tracking
                action_task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=ctx.workspace_id,
                    message_id=message_id,
                    execution_id=None,
                    pack_id="system",
                    task_type="auto_intent_extraction",
                    status=TaskStatus.SUCCEEDED,
                    params={
                        "action": "create_candidate_intents",
                        "candidate_intents_created": intents_created,
                        "auto_executed": True,
                        "note": "Candidate intents created as IntentTags. Only confirmed intents will be written to long-term memory."
                    },
                    result={"action": "create_candidate_intents", "candidate_intents_created": intents_created},
                    created_at=datetime.utcnow(),
                    started_at=datetime.utcnow(),
                    completed_at=datetime.utcnow(),
                    error=None
                )
                tasks_store.create_task(action_task)

                # Create completed TimelineItem (no CTA, already executed)
                timeline_item = TimelineItem(
                    id=str(uuid.uuid4()),
                    workspace_id=ctx.workspace_id,
                    message_id=message_id,
                    task_id=action_task.id,
                    type=TimelineItemType.INTENT_SEEDS,
                    title=self.i18n.t(
                        "conversation_orchestrator",
                        "timeline.intents_added_title" if intents_added > 0 else "timeline.no_intents_added_title",
                        count=intents_added,
                        default=f"Added {intents_added} intent(s) to Mindscape" if intents_added > 0 else "No new intents"
                    ),
                    summary=self.i18n.t(
                        "conversation_orchestrator",
                        "timeline.intents_added_summary" if intents_added > 0 else "timeline.all_intents_exist_summary",
                        count=intents_added,
                        default=f"Auto-added {intents_added} intent(s) from message" if intents_added > 0 else "All intents already exist"
                    ),
                    data={
                        "intents": intents_list,
                        "themes": themes_list,
                        "source": "auto_intent_extraction",
                        "intents_added": intents_added,
                        "auto_executed": True
                    },
                    cta=None,  # No CTA - already completed
                    created_at=datetime.utcnow()
                )

                self.timeline_items_store.create_timeline_item(timeline_item)
                logger.info(
                    f"Intent extractor auto-executed: created timeline item {timeline_item.id} "
                    f"with {intents_added} intents added"
                )
                return timeline_item
            else:
                # Don't auto-execute: create suggestion task (will show in PendingTasksPanel)
                # Similar to soft_write tasks - create task but don't create TimelineItem yet
                from ...models.workspace import Task, TaskStatus
                from ...services.stores.tasks_store import TasksStore

                tasks_store = TasksStore(self.store.db_path)

                # Create suggestion task
                suggestion_task = Task(
                    id=str(uuid.uuid4()),
                    workspace_id=ctx.workspace_id,
                    message_id=message_id,
                    execution_id=None,
                    pack_id="intent_extraction",
                    task_type="suggestion",
                    status=TaskStatus.PENDING,
                    params={
                        "intents": intents_list,
                        "themes": themes_list,
                        "source": "llm_extractor",
                        "requires_cta": True
                    },
                    result={
                        "suggestion": True,
                        "pack_id": "intent_extraction",
                        "requires_cta": True,
                        "llm_analysis": resolution_result.llm_analysis or {}
                    },
                    created_at=datetime.utcnow(),
                    started_at=None,
                    completed_at=None,
                    error=None
                )
                tasks_store.create_task(suggestion_task)

                logger.info(
                    f"Intent extractor created suggestion task {suggestion_task.id} "
                    f"for workspace {ctx.workspace_id} with {len(intents_list)} intents, {len(themes_list)} themes"
                )
                print(f"Intent extractor created suggestion task {suggestion_task.id} "
                      f"for workspace {ctx.workspace_id} with {len(intents_list)} intents, {len(themes_list)} themes", file=sys.stderr)

                # Don't create TimelineItem - it will be created after user confirms or auto-executes
                return None

        except Exception as e:
            logger.warning(
                f"Intent extractor failed (falling back to rule-based): {e}",
                exc_info=True
            )
            return None

    async def update_event_metadata(
        self,
        event_id: str,
        intents: List[Dict[str, Any]],
        themes: List[str]
    ) -> bool:
        """
        Update event metadata with extracted intents/themes

        Args:
            event_id: Event ID
            intents: List of intent dicts with title/summary
            themes: List of theme strings

        Returns:
            True if update succeeded, False otherwise
        """
        try:
            event = self.store.get_event(event_id)
            if not event:
                logger.warning(f"Event {event_id} not found for metadata update")
                return False

            if event.metadata is None:
                event.metadata = {}

            event.metadata["llm_extracted_intents"] = intents
            event.metadata["llm_extracted_themes"] = themes

            self.store.update_event(event_id, metadata=event.metadata)
            logger.debug(f"Updated event {event_id} metadata with extracted intents/themes")
            return True

        except Exception as e:
            logger.warning(f"Failed to update event metadata: {e}")
            return False

    def confirm_intent(self, intent_tag_id: str) -> bool:
        """
        Confirm an intent tag (candidate -> confirmed)

        Args:
            intent_tag_id: IntentTag ID

        Returns:
            True if confirmation succeeded
        """
        return self.intent_tags_store.confirm_intent(intent_tag_id)

    def reject_intent(self, intent_tag_id: str) -> bool:
        """
        Reject an intent tag (candidate -> rejected)

        Args:
            intent_tag_id: IntentTag ID

        Returns:
            True if rejection succeeded
        """
        return self.intent_tags_store.reject_intent(intent_tag_id)

    def extract_intents(self, workspace_id: str, profile_id: str, message: str, message_id: str) -> List[IntentTag]:
        """
        Extract intents and return candidate IntentTags

        DEPRECATED: Use extract_intents_with_ctx() instead.

        Args:
            workspace_id: Workspace ID
            profile_id: User profile ID
            message: User message text
            message_id: Message/event ID

        Returns:
            List of candidate IntentTags
        """
        from ...core.execution_context import ExecutionContext
        ctx = ExecutionContext(
            actor_id=profile_id,
            workspace_id=workspace_id,
            tags={"mode": "local"}
        )
        return self.extract_intents_with_ctx(ctx=ctx, message=message, message_id=message_id)

    def extract_intents_with_ctx(self, ctx: ExecutionContext, message: str, message_id: str) -> List[IntentTag]:
        """
        Extract intents and return candidate IntentTags using ExecutionContext

        Args:
            ctx: Execution context
            message: User message text
            message_id: Message/event ID

        Returns:
            List of candidate IntentTags
        """
        # Get candidate IntentTags for this message
        return self.intent_tags_store.list_intent_tags(
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            status=IntentTagStatus.CANDIDATE,
            limit=10
        )


