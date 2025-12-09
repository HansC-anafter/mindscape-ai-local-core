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
from backend.app.services.playbook_initializer import PlaybookInitializer
from backend.app.services.playbook_checkpoint_manager import PlaybookCheckpointManager
from backend.app.services.playbook_phase_manager import PlaybookPhaseManager
from backend.app.services.stores.playbook_executions_store import PlaybookExecutionsStore
from backend.app.models.execution_metadata import ExecutionMetadata
from backend.app.models.workspace import PlaybookExecution

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
            mindscape_store = store
        else:
            from backend.app.services.mindscape_store import MindscapeStore
            mindscape_store = MindscapeStore()
            self.workflow_orchestrator = WorkflowOrchestrator(store=mindscape_store)

        self.playbook_service = PlaybookService(store=mindscape_store)

        # Initialize Claude-style long-chain execution components
        db_path = mindscape_store.db_path if hasattr(mindscape_store, 'db_path') else None
        if db_path:
            self.executions_store = PlaybookExecutionsStore(db_path)
            self.checkpoint_manager = PlaybookCheckpointManager(self.executions_store)
            self.phase_manager = PlaybookPhaseManager(self.executions_store, None)  # Events store TBD
        else:
            self.executions_store = None
            self.checkpoint_manager = None
            self.phase_manager = None

        # Initialize initializer for first-time playbook execution
        self.initializer = PlaybookInitializer("/tmp/mindscape-workspace")  # Configurable path

    async def execute_playbook_run(
        self,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
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
            workspace_id: Optional workspace ID (required for multi-turn conversations)
            project_id: Optional project ID for sandbox context
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

            # Initialize Claude-style execution tracking
            execution_metadata = ExecutionMetadata()
            execution_metadata.set_execution_context(playbook_code=playbook_code)

            if self.executions_store:
                execution_record = PlaybookExecution(
                    id=execution_id,
                    workspace_id=workspace_id,
                    playbook_code=playbook_code,
                    intent_instance_id=None,  # Set from context if available
                    status="running",
                    phase="initialization",
                    last_checkpoint=None,
                    progress_log_path=None,
                    feature_list_path=None,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow()
                )
                self.executions_store.create_execution(execution_record)

                # Initialize playbook artifacts if first execution
                init_result = await self.initializer.initialize_playbook_execution(
                    execution_id=execution_record.id,
                    playbook_code=playbook_code,
                    workspace_id=workspace_id
                )

                if init_result["success"]:
                    execution_record.progress_log_path = init_result["artifacts"].get("progress_log")
                    execution_record.feature_list_path = init_result["artifacts"].get("feature_list")
                    # Update execution record with artifact paths
                    self.executions_store.update_execution_status(
                        execution_id=execution_record.id,
                        status="running",
                        phase="execution"
                    )

            execution_context = {
                "playbook_code": playbook_code,
                "playbook_name": playbook_run.playbook.metadata.name,
                "execution_id": execution_id,
                "total_steps": total_steps,
                "current_step_index": 0,
                "status": "running",
                "execution_metadata": execution_metadata.to_dict()
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
            logger.info(f"Executing {playbook_code} using PlaybookRunner (LLM conversation mode), workspace_id={workspace_id}, project_id={project_id}")

            result = await self.playbook_runner.start_playbook_execution(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=inputs,
                workspace_id=workspace_id,
                project_id=project_id,
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

