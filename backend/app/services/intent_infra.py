"""
Intent Infrastructure Service

Local Mindscape Intent Runtime (L0) - Workspace Intent Bridge

This service handles the bridge between Intent Governance Layer and Memory Layer,
specifically for converting intent candidates from LLM extraction into IntentCards
and TimelineItems in the local workspace.

Architecture Layers:
- L0: Local Mindscape Intent Runtime (this service)
- L1: Semantic-Hub Intent Infra (future, remote intent infrastructure)
- L2: Intent Infra Contract (shared domain contract)

The `intent_extraction` pack is an entry point to this service, not a playbook.
"""

import logging
import uuid
from typing import Dict, Any, Optional, List
from datetime import datetime

from backend.app.models.mindscape import IntentCard, IntentStatus, PriorityLevel
from backend.app.models.workspace import TaskStatus, TimelineItem, TimelineItemType
from backend.app.services.stores.timeline_items_store import TimelineItemsStore
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.i18n_service import get_i18n_service
from backend.app.core.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


class IntentInfraService:
    """
    Local Mindscape Intent Infrastructure Service (L0)

    Responsibilities:
    - Convert intent candidates from LLM extraction to IntentCards
    - Create TimelineItems for intent extraction activities
    - Provide workspace-level intent management
    - Bridge to semantic-hub Intent Infra (L1) when available

    This is the Workspace-side implementation of Intent Infra Contract (L2).
    """

    def __init__(
        self,
        store: MindscapeStore,
        default_locale: str = "zh-TW",
        semantic_backend: Optional[Any] = None
    ):
        """
        Initialize Intent Infrastructure Service

        Args:
            store: MindscapeStore instance
            default_locale: Default locale for i18n
            semantic_backend: Optional semantic-hub backend (future)
        """
        self.store = store
        self.default_locale = default_locale
        self.semantic_backend = semantic_backend
        self.timeline_items_store = TimelineItemsStore(store.db_path)
        self.i18n = get_i18n_service(default_locale=default_locale)

    async def handle_extraction_task(
        self,
        ctx: ExecutionContext,
        task: Any,
        original_message_id: str
    ) -> Dict[str, Any]:
        """
        Handle intent_extraction task execution

        Converts intent candidates from task params into IntentCards and TimelineItems.
        This is the main entry point for the `intent_extraction` pack.

        Args:
            ctx: Execution context
            task: Task record containing intents/themes in params
            original_message_id: Original message/event ID

        Returns:
            Result dict with pack_id and intents_added count
        """
        if not task:
            logger.warning("handle_extraction_task called without task")
            return {"pack_id": "intent_extraction", "intents_added": 0}

        intents = task.params.get("intents", []) if task.params else []
        themes = task.params.get("themes", []) if task.params else []

        if not intents:
            logger.info(f"No intents to process for task {task.id}")
            return {"pack_id": "intent_extraction", "intents_added": 0}

        intents_added = await self._create_intent_cards_from_candidates(
            ctx=ctx,
            intent_candidates=intents,
            task_id=task.id,
            workspace_id=ctx.workspace_id
        )

        # Create project from intents if we have valid intents
        project_id = None
        if intents_added > 0 and intents:
            project_id = await self._create_project_from_intent(
                ctx=ctx,
                intent_candidates=intents,
                workspace_id=ctx.workspace_id
            )

        timeline_item = await self._create_timeline_for_extraction(
            ctx=ctx,
            original_message_id=original_message_id,
            task_id=task.id,
            intents=intents,
            themes=themes,
            intents_added=intents_added
        )

        if self.semantic_backend:
            await self._sync_to_semantic_hub(
                ctx=ctx,
                intents=intents,
                themes=themes
            )

        return {
            "pack_id": "intent_extraction",
            "intents_added": intents_added,
            "timeline_item_id": timeline_item.id if timeline_item else None,
            "project_id": project_id
        }

    async def _create_intent_cards_from_candidates(
        self,
        ctx: ExecutionContext,
        intent_candidates: List[Any],
        task_id: str,
        workspace_id: str
    ) -> int:
        """
        Create IntentCards from intent candidates

        Args:
            ctx: Execution context
            intent_candidates: List of intent candidates (dict or str)
            task_id: Task ID for metadata
            workspace_id: Workspace ID

        Returns:
            Number of intents added
        """
        intents_added = 0

        for intent_item in intent_candidates[:3]:
            if isinstance(intent_item, dict):
                intent_text = intent_item.get("title") or intent_item.get("text") or str(intent_item)
            else:
                intent_text = str(intent_item) if intent_item else None

            if not intent_text or not isinstance(intent_text, str) or len(intent_text.strip()) == 0:
                continue

            try:
                existing_intents = self.store.list_intents(
                    profile_id=ctx.actor_id,
                    status=None,
                    priority=None
                )
                intent_exists = any(
                    intent.title == intent_text.strip() or
                    intent_text.strip() in intent.title
                    for intent in existing_intents
                )

                if not intent_exists:
                    new_intent = IntentCard(
                        id=str(uuid.uuid4()),
                        profile_id=ctx.actor_id,
                        title=intent_text.strip(),
                        description="Added from intent extraction task",
                        status=IntentStatus.PAUSED,  # Use PAUSED status so it appears as CANDIDATE in API and shows in DecisionPanel
                        priority=PriorityLevel.MEDIUM,
                        tags=[],
                        category="intent_extraction",
                        progress_percentage=0.0,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        started_at=None,
                        completed_at=None,
                        due_date=None,
                        parent_intent_id=None,
                        child_intent_ids=[],
                        metadata={
                            "source": "intent_extraction_task",
                            "workspace_id": workspace_id,
                            "task_id": task_id
                        }
                    )
                    self.store.create_intent(new_intent)
                    intents_added += 1
                    logger.info(f"Created IntentCard from extraction task: {intent_text[:50]}")
            except Exception as e:
                logger.warning(f"Failed to create IntentCard from candidate: {e}")

        return intents_added

    async def _create_timeline_for_extraction(
        self,
        ctx: ExecutionContext,
        original_message_id: str,
        task_id: str,
        intents: List[Any],
        themes: List[Any],
        intents_added: int
    ) -> Optional[TimelineItem]:
        """
        Create TimelineItem for intent extraction activity

        Args:
            ctx: Execution context
            original_message_id: Original message/event ID
            task_id: Task ID
            intents: List of intents
            themes: List of themes
            intents_added: Number of intents added

        Returns:
            Created TimelineItem or None
        """
        try:
            timeline_item = TimelineItem(
                id=str(uuid.uuid4()),
                workspace_id=ctx.workspace_id,
                message_id=original_message_id,
                task_id=task_id,
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
                    default=f"Added {intents_added} intent(s) from message" if intents_added > 0 else "All intents already exist"
                ),
                data={
                    "intents": intents,
                    "themes": themes,
                    "source": "intent_extraction_task",
                    "intents_added": intents_added
                },
                cta=None,
                created_at=datetime.utcnow()
            )
            self.timeline_items_store.create_timeline_item(timeline_item)
            logger.info(f"Created TimelineItem for intent extraction: {timeline_item.id}")
            return timeline_item
        except Exception as e:
            logger.error(f"Failed to create TimelineItem for extraction: {e}", exc_info=True)
            return None

    async def _create_project_from_intent(
        self,
        ctx: ExecutionContext,
        intent_candidates: List[Any],
        workspace_id: str
    ) -> Optional[str]:
        """
        Create project from intent candidates

        Args:
            ctx: Execution context
            intent_candidates: List of intent candidates with confidence
            workspace_id: Workspace ID

        Returns:
            Project ID if created, None otherwise
        """
        if not intent_candidates:
            return None

        try:
            # Get primary intent (highest confidence or first)
            primary_intent = max(
                intent_candidates,
                key=lambda x: x.get('confidence', 0.0) if isinstance(x, dict) else 0.0,
                default=intent_candidates[0]
            )

            if isinstance(primary_intent, dict):
                intent_title = primary_intent.get('title') or primary_intent.get('text') or str(primary_intent)
                intent_confidence = primary_intent.get('confidence', 0.0)
            else:
                intent_title = str(primary_intent)
                intent_confidence = 0.0

            # Use ProjectDetector to determine project type and flow_id
            from backend.app.services.project.project_detector import ProjectDetector
            from backend.app.services.project.project_manager import ProjectManager
            from backend.app.models.workspace import Workspace

            workspace = self.store.get_workspace(workspace_id)
            if not workspace:
                logger.warning(f"Workspace {workspace_id} not found, cannot create project")
                return None

            # Create ProjectDetector with store
            project_detector = ProjectDetector()
            project_manager = ProjectManager(self.store)

            # Build simplified context for project detection
            # Use intent title as the message
            context = [{"role": "user", "content": intent_title}]
            suggestion = await project_detector.detect(
                message=intent_title,
                conversation_context=context,
                workspace=workspace
            )

            if not suggestion or suggestion.mode != "project":
                logger.info(f"Project detection returned mode={suggestion.mode if suggestion else 'None'}, skipping project creation")
                return None
            else:
                project_type = suggestion.project_type
                # flow_id will be auto-generated by ProjectManager
                project_title = suggestion.project_title or intent_title[:100]

                if not project_type or not project_title:
                    logger.warning("Project suggestion missing required fields (project_type or project_title)")
                    return None

            # Check for duplicate projects using LLM
            existing_projects = await project_manager.list_projects(
                workspace_id=workspace_id,
                state="open"
            )

            duplicate_project = None
            if existing_projects:
                duplicate_project = await project_detector.check_duplicate(
                    suggested_project=suggestion,
                    existing_projects=existing_projects,
                    workspace=workspace
                )

            if duplicate_project:
                logger.info(f"LLM detected duplicate project: {duplicate_project.id}, using existing project")
                # Even for duplicate projects, check if we should execute playbook flow
                # Get playbook_sequence from suggestion
                playbook_sequence = suggestion.playbook_sequence if suggestion and hasattr(suggestion, 'playbook_sequence') else None
                if playbook_sequence and len(playbook_sequence) > 0:
                    try:
                        from backend.app.services.project.flow_executor import FlowExecutor
                        flow_executor = FlowExecutor(store=self.store, project_manager=project_manager)

                        # Execute flow in background to avoid blocking
                        import asyncio
                        asyncio.create_task(
                            self._execute_playbook_flow_async(
                                flow_executor=flow_executor,
                                project_id=duplicate_project.id,
                                workspace_id=workspace_id,
                                profile_id=ctx.actor_id
                            )
                        )
                        logger.info(f"Scheduled playbook flow execution for duplicate project {duplicate_project.id} with {len(playbook_sequence)} playbooks")
                    except Exception as e:
                        logger.error(f"Failed to schedule playbook flow execution for duplicate project {duplicate_project.id}: {e}", exc_info=True)
                return duplicate_project.id

            # Get flow_id from suggestion if available
            flow_id = getattr(suggestion, 'flow_id', None) if suggestion else None

            # Ensure flow exists, create if not
            if flow_id:
                from backend.app.services.stores.playbook_flows_store import PlaybookFlowsStore
                from backend.app.models.playbook_flow import PlaybookFlow
                flows_store = PlaybookFlowsStore(self.store.db_path)
                flow = flows_store.get_flow(flow_id)

                if not flow:
                    logger.info(f"Flow {flow_id} not found, creating flow")
                    # Use playbook_sequence from suggestion if available, and validate it
                    from backend.app.services.project.playbook_validator import validate_playbook_sequence
                    from pathlib import Path

                    raw_playbook_sequence = suggestion.playbook_sequence if suggestion and hasattr(suggestion, 'playbook_sequence') else []
                    base_dir = Path(__file__).parent.parent.parent.parent
                    validated_playbook_sequence = validate_playbook_sequence(raw_playbook_sequence, base_dir)

                    flow = PlaybookFlow(
                        id=flow_id,
                        name=f"{project_type} Flow" if project_type else "Flow",
                        description=f"Flow for {project_type} projects" if project_type else "Default flow",
                        flow_definition={
                            "nodes": [],
                            "edges": [],
                            "playbook_sequence": validated_playbook_sequence
                        },
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow()
                    )
                    flows_store.create_flow(flow)
                    logger.info(f"Created flow: {flow_id} with {len(validated_playbook_sequence)} validated playbooks")

            # flow_id will be auto-generated by ProjectManager if not provided
            # Create project
            playbook_sequence = suggestion.playbook_sequence if suggestion and hasattr(suggestion, 'playbook_sequence') else None
            project = await project_manager.create_project(
                project_type=project_type,
                title=project_title,
                workspace_id=workspace_id,
                flow_id=None,  # Will be auto-generated
                initiator_user_id=ctx.actor_id,
                metadata={
                    "created_from": "intent_extraction",
                    "primary_intent": intent_title,
                    "intent_confidence": intent_confidence
                },
                playbook_sequence=playbook_sequence
            )

            # Update workspace primary_project_id if not set
            if not workspace.primary_project_id:
                workspace.primary_project_id = project.id
                self.store.update_workspace(workspace)
                logger.info(f"Set workspace {workspace_id} primary_project_id to {project.id}")

            logger.info(f"Created project {project.id} from intent extraction: {project_title}")

            # Execute playbook flow if playbook_sequence exists
            if playbook_sequence and len(playbook_sequence) > 0:
                try:
                    from backend.app.services.project.flow_executor import FlowExecutor
                    flow_executor = FlowExecutor(store=self.store, project_manager=project_manager)

                    # Execute flow in background to avoid blocking
                    import asyncio
                    asyncio.create_task(
                        self._execute_playbook_flow_async(
                            flow_executor=flow_executor,
                            project_id=project.id,
                            workspace_id=workspace_id,
                            profile_id=ctx.actor_id
                        )
                    )
                    logger.info(f"Scheduled playbook flow execution for project {project.id} with {len(playbook_sequence)} playbooks")
                except Exception as e:
                    logger.error(f"Failed to schedule playbook flow execution for project {project.id}: {e}", exc_info=True)
                    # Don't fail project creation if playbook execution scheduling fails

            return project.id

        except Exception as e:
            logger.error(f"Failed to create project from intent: {e}", exc_info=True)
            return None

    async def _execute_playbook_flow_async(
        self,
        flow_executor,
        project_id: str,
        workspace_id: str,
        profile_id: str
    ):
        """
        Execute playbook flow asynchronously after project creation

        Args:
            flow_executor: FlowExecutor instance
            project_id: Project ID
            workspace_id: Workspace ID
            profile_id: User profile ID
        """
        try:
            logger.info(f"Starting playbook flow execution for project {project_id}")
            execution_result = await flow_executor.execute_flow(
                project_id=project_id,
                workspace_id=workspace_id,
                profile_id=profile_id
            )
            logger.info(f"Completed playbook flow execution for project {project_id}: {execution_result}")
        except Exception as e:
            logger.error(f"Failed to execute playbook flow for project {project_id}: {e}", exc_info=True)

    async def _sync_to_semantic_hub(
        self,
        ctx: ExecutionContext,
        intents: List[Any],
        themes: List[Any]
    ):
        """
        Sync intents to semantic-hub Intent Infra (L1)

        This is a placeholder for future integration with semantic-hub.
        When semantic_backend is configured, this will push intents to the remote infrastructure.

        Args:
            ctx: Execution context
            intents: List of intents
            themes: List of themes
        """
        if not self.semantic_backend:
            return

        try:
            await self.semantic_backend.push_intents(
                workspace_id=ctx.workspace_id,
                profile_id=ctx.actor_id,
                intents=intents,
                themes=themes
            )
            logger.info(f"Synced {len(intents)} intents to semantic-hub")
        except Exception as e:
            logger.warning(f"Failed to sync intents to semantic-hub: {e}")

    async def create_intent_card(
        self,
        ctx: ExecutionContext,
        payload: Dict[str, Any]
    ) -> Optional[IntentCard]:
        """
        Create an IntentCard from payload

        This is part of the Intent Infra Contract (L2) interface.

        Args:
            ctx: Execution context
            payload: Intent card data

        Returns:
            Created IntentCard or None
        """
        try:
            intent_card = IntentCard(
                id=str(uuid.uuid4()),
                profile_id=ctx.actor_id,
                title=payload.get("title", ""),
                description=payload.get("description", ""),
                status=IntentStatus.ACTIVE,
                priority=PriorityLevel.MEDIUM,
                tags=payload.get("tags", []),
                category=payload.get("category"),
                progress_percentage=0.0,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
                started_at=None,
                completed_at=None,
                due_date=None,
                parent_intent_id=None,
                child_intent_ids=[],
                metadata=payload.get("metadata", {})
            )
            created = self.store.create_intent(intent_card)
            logger.info(f"Created IntentCard via IntentInfraService: {created.id}")
            return created
        except Exception as e:
            logger.error(f"Failed to create IntentCard: {e}", exc_info=True)
            return None

    async def list_intents(
        self,
        ctx: ExecutionContext,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[IntentCard]:
        """
        List intents with optional filters

        This is part of the Intent Infra Contract (L2) interface.

        Args:
            ctx: Execution context
            filters: Optional filters (status, priority, category, etc.)

        Returns:
            List of IntentCard
        """
        try:
            status = filters.get("status") if filters else None
            priority = filters.get("priority") if filters else None
            category = filters.get("category") if filters else None

            intents = self.store.list_intents(
                profile_id=ctx.actor_id,
                status=status,
                priority=priority
            )

            if category:
                intents = [i for i in intents if i.category == category]

            return intents
        except Exception as e:
            logger.error(f"Failed to list intents: {e}", exc_info=True)
            return []

