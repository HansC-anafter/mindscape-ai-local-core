"""
Playbook Run Executor
Unified executor for playbook.run = playbook.md + playbook.json

Automatically selects execution mode based on available components:
- If playbook.json exists: use WorkflowOrchestrator (structured workflow)
- If only playbook.md exists: use PlaybookRunner (LLM conversation)

DEPRECATED: Legacy playbook execution, scheduled for removal after P2.
Do not add new dependencies. Use PlaybookService.execute_playbook() instead.
This class is only used internally by PlaybookService for backward compatibility.
"""

import logging
from typing import Dict, Any, Optional

from backend.app.models.playbook import PlaybookRun, PlaybookKind
from backend.app.services.playbook_runner import PlaybookRunner
from backend.app.services.workflow_orchestrator import WorkflowOrchestrator
from backend.app.services.playbook_service import PlaybookService

logger = logging.getLogger(__name__)


class PlaybookRunExecutor:
    """Unified executor for playbook.run"""

    def __init__(self, store=None):
        """
        Initialize PlaybookRunExecutor

        Args:
            store: MindscapeStore instance (optional)
        """
        self.store = store
        self.playbook_runner = PlaybookRunner()
        if store:
            self.workflow_orchestrator = WorkflowOrchestrator(store=store)
        else:
            from backend.app.services.mindscape_store import MindscapeStore
            store = MindscapeStore()
            self.workflow_orchestrator = WorkflowOrchestrator(store=store)

        self.playbook_service = PlaybookService(store=store)

    async def execute_playbook_run(
        self,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
        target_language: Optional[str] = None,
        variant_id: Optional[str] = None,
        locale: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute playbook.run with appropriate runtime

        Args:
            playbook_code: Playbook code
            profile_id: User profile ID
            inputs: Execution inputs
            workspace_id: Optional workspace ID
            target_language: Target language for output
            variant_id: Optional personalized variant ID
            locale: Preferred locale for playbook.md

        Returns:
            Execution result dict
        """
        # Load playbook.run via PlaybookService
        playbook_run = await self.playbook_service.load_playbook_run(
            playbook_code=playbook_code,
            locale=locale or 'zh-TW',
            workspace_id=workspace_id
        )

        if not playbook_run:
            raise ValueError(f"Playbook not found: {playbook_code}")

        execution_mode = playbook_run.get_execution_mode()
        logger.info(f"PlaybookRunExecutor: playbook_code={playbook_code}, execution_mode={execution_mode}, has_json={playbook_run.has_json()}")

        if execution_mode == 'workflow' and playbook_run.playbook_json:
            logger.info(f"PlaybookRunExecutor: Executing {playbook_code} using WorkflowOrchestrator (playbook.json found)")

            # Validate workspace_id - must not be None
            if not workspace_id:
                error_msg = f"workspace_id is required for playbook execution: {playbook_code}"
                logger.error(f"PlaybookRunExecutor: {error_msg}")
                raise ValueError(error_msg)

            import uuid
            from datetime import datetime
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.services.mindscape_store import MindscapeStore
            from backend.app.models.workspace import Task, TaskStatus

            execution_id = str(uuid.uuid4())
            store = MindscapeStore()
            tasks_store = TasksStore(store.db_path)
            total_steps = len(playbook_run.playbook_json.steps) if playbook_run.playbook_json.steps else 1

            execution_context = {
                "playbook_code": playbook_code,
                "playbook_name": playbook_run.playbook.metadata.name,
                "execution_id": execution_id,
                "total_steps": total_steps,
                "current_step_index": 0,
                "status": "running"
            }

            logger.info(f"PlaybookRunExecutor: Creating execution task {execution_id} for playbook {playbook_code}, workspace_id={workspace_id}, total_steps={total_steps}")

            task = Task(
                id=execution_id,
                workspace_id=workspace_id,
                message_id=str(uuid.uuid4()),
                execution_id=execution_id,
                profile_id=profile_id,
                pack_id=playbook_code,
                task_type="playbook_execution",
                status=TaskStatus.RUNNING,
                execution_context=execution_context,
                created_at=datetime.utcnow(),
                started_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )

            tasks_store.create_task(task)
            logger.info(f"PlaybookRunExecutor: Created execution task {execution_id} for {playbook_code}")

            from backend.app.models.playbook import HandoffPlan, WorkflowStep

            workflow_step = WorkflowStep(
                playbook_code=playbook_code,
                kind=playbook_run.playbook_json.kind,
                inputs=inputs or {},
                interaction_mode=playbook_run.playbook.metadata.interaction_mode
            )

            handoff_plan = HandoffPlan(
                steps=[workflow_step],
                context=inputs or {}
            )

            try:
                result = await self.workflow_orchestrator.execute_workflow(
                    handoff_plan,
                    execution_id=execution_id,
                    workspace_id=workspace_id,
                    profile_id=profile_id
                )

                execution_context["status"] = "completed"
                execution_context["current_step_index"] = total_steps
                completed_at = datetime.utcnow()
                tasks_store.update_task(
                    task.id,
                    execution_context=execution_context,
                    status=TaskStatus.SUCCEEDED,
                    completed_at=completed_at
                )
                logger.info(f"PlaybookRunExecutor: Execution {execution_id} completed successfully")
            except Exception as e:
                from backend.app.shared.error_handler import parse_api_error

                error_info = parse_api_error(e)
                execution_context["status"] = "failed"
                execution_context["error"] = error_info.user_message
                execution_context["error_details"] = error_info.to_dict()
                completed_at = datetime.utcnow()
                tasks_store.update_task(
                    task.id,
                    execution_context=execution_context,
                    status=TaskStatus.FAILED,
                    completed_at=completed_at,
                    error=error_info.user_message
                )
                logger.error(f"PlaybookRunExecutor: Execution {execution_id} failed: {e}")
                raise

            return {
                "execution_mode": "workflow",
                "playbook_code": playbook_code,
                "execution_id": execution_id,
                "result": result,
                "has_json": True
            }

        else:
            logger.info(f"Executing {playbook_code} using PlaybookRunner (LLM conversation mode)")

            result = await self.playbook_runner.start_playbook_execution(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                target_language=target_language,
                variant_id=variant_id
            )

            return {
                "execution_mode": "conversation",
                "playbook_code": playbook_code,
                "result": result,
                "has_json": False
            }

    async def get_playbook_run(self, playbook_code: str, locale: Optional[str] = None) -> Optional[PlaybookRun]:
        """
        Get playbook.run definition without executing

        Args:
            playbook_code: Playbook code
            locale: Preferred locale

        Returns:
            PlaybookRun or None if not found
        """
        # Load playbook.run via PlaybookService
        return await self.playbook_service.load_playbook_run(
            playbook_code=playbook_code,
            locale=locale or 'zh-TW',
            workspace_id=None
        )

