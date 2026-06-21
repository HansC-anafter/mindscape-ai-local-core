"""Project creation and flow scheduling helpers for intent infrastructure."""

from __future__ import annotations

import logging
from typing import Any, List, Optional

from backend.app.core.domain_context import LocalDomainContext
from backend.app.services.intent_infra_core.time import _utc_now

logger = logging.getLogger(__name__)


class ProjectIntentMixin:
    """Project and flow helper methods for IntentInfraService."""

    async def _create_project_from_intent(
        self,
        ctx: LocalDomainContext,
        intent_candidates: List[Any],
        workspace_id: str,
    ) -> Optional[str]:
        """
        Create project from intent candidates.

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
            primary_intent = max(
                intent_candidates,
                key=lambda item: (
                    item.get("confidence", 0.0) if isinstance(item, dict) else 0.0
                ),
                default=intent_candidates[0],
            )

            if isinstance(primary_intent, dict):
                intent_title = (
                    primary_intent.get("title")
                    or primary_intent.get("text")
                    or str(primary_intent)
                )
                intent_confidence = primary_intent.get("confidence", 0.0)
            else:
                intent_title = str(primary_intent)
                intent_confidence = 0.0

            from backend.app.services.project.project_detector import ProjectDetector
            from backend.app.services.project.project_manager import ProjectManager

            workspace = await self.store.get_workspace(workspace_id)
            if not workspace:
                logger.warning(
                    f"Workspace {workspace_id} not found, cannot create project"
                )
                return None

            project_detector = ProjectDetector()
            project_manager = ProjectManager(self.store)

            context = [{"role": "user", "content": intent_title}]
            from backend.app.services.playbook_service import PlaybookService

            playbook_service = PlaybookService(store=self.store)
            available_playbooks_metadata = await playbook_service.list_playbooks(
                workspace_id=workspace_id,
                locale=self.default_locale or "zh-TW",
            )
            available_playbooks = [
                {
                    "playbook_code": playbook.playbook_code,
                    "name": playbook.name,
                    "description": playbook.description,
                }
                for playbook in available_playbooks_metadata
            ]

            suggestion = await project_detector.detect(
                message=intent_title,
                conversation_context=context,
                workspace=workspace,
                available_playbooks=available_playbooks,
            )

            if not suggestion or suggestion.mode != "project":
                logger.info(
                    "Project detection returned mode="
                    f"{suggestion.mode if suggestion else 'None'}, skipping project creation"
                )
                return None

            project_type = suggestion.project_type
            project_title = suggestion.project_title or intent_title[:100]

            if not project_type or not project_title:
                logger.warning(
                    "Project suggestion missing required fields "
                    "(project_type or project_title)"
                )
                return None

            existing_projects = await project_manager.list_projects(
                workspace_id=workspace_id,
                state="open",
            )

            duplicate_project = None
            if existing_projects:
                duplicate_project = await project_detector.check_duplicate(
                    suggested_project=suggestion,
                    existing_projects=existing_projects,
                    workspace=workspace,
                )

            if duplicate_project:
                logger.info(
                    f"LLM detected duplicate project: {duplicate_project.id}, "
                    "using existing project"
                )
                playbook_sequence = (
                    suggestion.playbook_sequence
                    if suggestion and hasattr(suggestion, "playbook_sequence")
                    else None
                )
                if playbook_sequence and len(playbook_sequence) > 0:
                    try:
                        from backend.app.services.project.flow_executor import (
                            FlowExecutor,
                        )

                        flow_executor = FlowExecutor(
                            store=self.store,
                            project_manager=project_manager,
                        )

                        import asyncio

                        asyncio.create_task(
                            self._execute_playbook_flow_async(
                                flow_executor=flow_executor,
                                project_id=duplicate_project.id,
                                workspace_id=workspace_id,
                                profile_id=ctx.actor_id,
                            )
                        )
                        logger.info(
                            "Scheduled playbook flow execution for duplicate project "
                            f"{duplicate_project.id} with {len(playbook_sequence)} playbooks"
                        )
                    except Exception as exc:
                        logger.error(
                            "Failed to schedule playbook flow execution for "
                            f"duplicate project {duplicate_project.id}: {exc}",
                            exc_info=True,
                        )
                return duplicate_project.id

            flow_id = getattr(suggestion, "flow_id", None) if suggestion else None

            if flow_id:
                from pathlib import Path

                from backend.app.models.playbook_flow import PlaybookFlow
                from backend.app.services.project.playbook_validator import (
                    validate_playbook_sequence,
                )
                from backend.app.services.stores.playbook_flows_store import (
                    PlaybookFlowsStore,
                )

                flows_store = PlaybookFlowsStore(self.store.db_path)
                flow = flows_store.get_flow(flow_id)

                if not flow:
                    logger.info(f"Flow {flow_id} not found, creating flow")
                    raw_playbook_sequence = (
                        suggestion.playbook_sequence
                        if suggestion and hasattr(suggestion, "playbook_sequence")
                        else []
                    )
                    base_dir = Path(__file__).parent.parent.parent.parent.parent
                    validated_playbook_sequence = validate_playbook_sequence(
                        raw_playbook_sequence,
                        base_dir,
                    )

                    flow = PlaybookFlow(
                        id=flow_id,
                        name=f"{project_type} Flow" if project_type else "Flow",
                        description=(
                            f"Flow for {project_type} projects"
                            if project_type
                            else "Default flow"
                        ),
                        flow_definition={
                            "nodes": [],
                            "edges": [],
                            "playbook_sequence": validated_playbook_sequence,
                        },
                        created_at=_utc_now(),
                        updated_at=_utc_now(),
                    )
                    flows_store.create_flow(flow)
                    logger.info(
                        f"Created flow: {flow_id} with "
                        f"{len(validated_playbook_sequence)} validated playbooks"
                    )

            playbook_sequence = (
                suggestion.playbook_sequence
                if suggestion and hasattr(suggestion, "playbook_sequence")
                else None
            )
            project = await project_manager.create_project(
                project_type=project_type,
                title=project_title,
                workspace_id=workspace_id,
                flow_id=None,
                initiator_user_id=ctx.actor_id,
                metadata={
                    "created_from": "intent_extraction",
                    "primary_intent": intent_title,
                    "intent_confidence": intent_confidence,
                },
                playbook_sequence=playbook_sequence,
            )

            if not workspace.primary_project_id:
                workspace.primary_project_id = project.id
                await self.store.update_workspace(workspace)
                logger.info(f"Set workspace {workspace_id} primary_project_id to {project.id}")

            logger.info(
                f"Created project {project.id} from intent extraction: {project_title}"
            )

            if playbook_sequence and len(playbook_sequence) > 0:
                try:
                    from backend.app.services.project.flow_executor import FlowExecutor

                    flow_executor = FlowExecutor(
                        store=self.store,
                        project_manager=project_manager,
                    )

                    import asyncio

                    asyncio.create_task(
                        self._execute_playbook_flow_async(
                            flow_executor=flow_executor,
                            project_id=project.id,
                            workspace_id=workspace_id,
                            profile_id=ctx.actor_id,
                        )
                    )
                    logger.info(
                        f"Scheduled playbook flow execution for project {project.id} "
                        f"with {len(playbook_sequence)} playbooks"
                    )
                except Exception as exc:
                    logger.error(
                        f"Failed to schedule playbook flow execution for project "
                        f"{project.id}: {exc}",
                        exc_info=True,
                    )

            return project.id

        except Exception as exc:
            logger.error(f"Failed to create project from intent: {exc}", exc_info=True)
            return None

    async def _execute_playbook_flow_async(
        self,
        flow_executor,
        project_id: str,
        workspace_id: str,
        profile_id: str,
    ):
        """
        Execute playbook flow asynchronously after project creation.

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
                profile_id=profile_id,
            )
            logger.info(
                f"Completed playbook flow execution for project {project_id}: "
                f"{execution_result}"
            )
        except Exception as exc:
            logger.error(
                f"Failed to execute playbook flow for project {project_id}: {exc}",
                exc_info=True,
            )
