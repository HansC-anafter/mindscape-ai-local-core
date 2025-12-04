"""
Playbook Service
Unified service layer for all playbook operations
Similar to Intent Server, provides unified API interface
"""

import logging
from typing import List, Optional, Dict, Any
from enum import Enum

from backend.app.models.playbook import Playbook, PlaybookMetadata
from backend.app.services.playbook_registry import PlaybookRegistry, PlaybookSource
from backend.app.services.playbook_loaders import PlaybookJsonLoader

logger = logging.getLogger(__name__)


class ExecutionMode(str, Enum):
    """Execution mode"""
    SYNC = "sync"  # Synchronous execution, wait for completion
    ASYNC = "async"  # Asynchronous execution, return execution_id immediately
    STREAM = "stream"  # Stream execution, return events in real-time


class ExecutionResult:
    """Execution result (simplified for now)"""
    def __init__(
        self,
        execution_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        progress: float = 0.0
    ):
        self.execution_id = execution_id
        self.status = status
        self.result = result
        self.error = error
        self.progress = progress


class PlaybookService:
    """
    Unified service layer for all playbook operations
    Similar to Intent Server, provides unified API interface
    """

    def __init__(self, store=None):
        """
        Initialize PlaybookService

        Args:
            store: MindscapeStore instance (optional, for user playbooks and state management)
        """
        self.store = store
        self.registry = PlaybookRegistry(store)

    async def get_playbook(
        self,
        playbook_code: str,
        locale: str = "zh-TW",
        workspace_id: Optional[str] = None,
    ) -> Optional[Playbook]:
        """
        Get playbook details

        Args:
            playbook_code: Playbook code
            locale: Language locale (default: zh-TW)
            workspace_id: Workspace ID (optional, for priority: user > capability > system)

        Returns:
            Playbook object or None
        """
        # Log the locale being passed
        logger.info(f"PlaybookService.get_playbook called: code={playbook_code}, locale={locale}, workspace_id={workspace_id}")
        if locale is None:
            import traceback
            logger.error(f"PlaybookService.get_playbook: locale is None for {playbook_code}! Stack trace:\n{traceback.format_stack()}")
            raise ValueError(f"locale cannot be None when calling get_playbook for {playbook_code}")

        playbook = await self.registry.get_playbook(playbook_code, locale, workspace_id)
        return playbook

    async def list_playbooks(
        self,
        workspace_id: Optional[str] = None,
        locale: Optional[str] = None,
        category: Optional[str] = None,
        source: Optional[PlaybookSource] = None,
        tags: Optional[List[str]] = None,
    ) -> List[PlaybookMetadata]:
        """
        List all available playbooks

        Args:
            workspace_id: Workspace ID (optional)
            locale: Language locale (optional)
            category: Category filter (optional)
            source: Source filter (system, capability, user)
            tags: Tags filter (optional, for P1.5 attribute mapping)

        Returns:
            List of playbook metadata
        """
        return await self.registry.list_playbooks(
            workspace_id=workspace_id,
            locale=locale,
            category=category,
            source=source,
            tags=tags
        )

    async def execute_playbook(
        self,
        playbook_code: str,
        workspace_id: str,
        profile_id: str,
        inputs: Dict[str, Any],
        execution_mode: ExecutionMode = ExecutionMode.ASYNC
    ) -> ExecutionResult:
        """
        Execute playbook

        Args:
            playbook_code: Playbook code
            workspace_id: Workspace ID
            profile_id: Profile ID
            inputs: Input parameters
            execution_mode: Execution mode (sync, async, stream)

        Returns:
            ExecutionResult object
        """
        playbook = await self.get_playbook(playbook_code, workspace_id=workspace_id)
        if not playbook:
            raise ValueError(f"Playbook not found: {playbook_code}")

        from backend.app.services.playbook_run_executor import PlaybookRunExecutor

        playbook_run_executor = PlaybookRunExecutor()
        executor_inputs = inputs or {}
        locale = executor_inputs.get('locale') or 'zh-TW'

        try:
            execution_result_dict = await playbook_run_executor.execute_playbook_run(
                playbook_code=playbook_code,
                profile_id=profile_id,
                inputs=executor_inputs,
                workspace_id=workspace_id,
                target_language=executor_inputs.get('target_language'),
                locale=locale
            )

            execution_id = execution_result_dict.get('execution_id') or execution_result_dict.get('result', {}).get('execution_id')
            if not execution_id:
                import uuid
                execution_id = str(uuid.uuid4())

            status = execution_result_dict.get('status', 'running')
            if 'execution_mode' in execution_result_dict:
                status = 'running'

            logger.info(f"PlaybookService: Executed playbook {playbook_code}, execution_id={execution_id}, status={status}")

            return ExecutionResult(
                execution_id=execution_id,
                status=status,
                result=execution_result_dict,
                progress=execution_result_dict.get('progress', 0.0)
            )

        except Exception as e:
            logger.error(f"PlaybookService: Failed to execute playbook {playbook_code}: {e}", exc_info=True)
            import uuid
            from backend.app.shared.error_handler import parse_api_error

            error_info = parse_api_error(e)
            execution_id = str(uuid.uuid4())

            return ExecutionResult(
                execution_id=execution_id,
                status="error",
                result=None,
                error=error_info.user_message,  # Use user-friendly message
                progress=0.0
            )

    async def get_execution_status(
        self,
        execution_id: str
    ) -> Optional[str]:
        """
        Get execution status

        Args:
            execution_id: Execution ID

        Returns:
            Execution status or None
        """
        if not self.store:
            logger.warning("PlaybookService.get_execution_status() requires store")
            return None

        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import TaskStatus

            tasks_store = TasksStore(self.store.db_path)
            task = tasks_store.get_task(execution_id)

            if task:
                status_map = {
                    TaskStatus.PENDING: "pending",
                    TaskStatus.RUNNING: "running",
                    TaskStatus.SUCCEEDED: "completed",
                    TaskStatus.FAILED: "failed",
                    TaskStatus.CANCELLED: "cancelled"
                }
                return status_map.get(task.status, "unknown")

            return None
        except Exception as e:
            logger.error(f"PlaybookService: Failed to get execution status for {execution_id}: {e}", exc_info=True)
            return None

    async def get_execution_result(
        self,
        execution_id: str
    ) -> Optional[ExecutionResult]:
        """
        Get execution result

        Args:
            execution_id: Execution ID

        Returns:
            ExecutionResult or None
        """
        if not self.store:
            logger.warning("PlaybookService.get_execution_result() requires store")
            return None

        try:
            from backend.app.services.stores.tasks_store import TasksStore
            from backend.app.models.workspace import TaskStatus

            tasks_store = TasksStore(self.store.db_path)
            task = tasks_store.get_task(execution_id)

            if not task:
                return None

            status_map = {
                TaskStatus.PENDING: "pending",
                TaskStatus.RUNNING: "running",
                TaskStatus.SUCCEEDED: "completed",
                TaskStatus.FAILED: "failed",
                TaskStatus.CANCELLED: "cancelled"
            }
            status = status_map.get(task.status, "unknown")

            result = None
            error = None
            progress = 0.0

            if task.execution_context:
                result = task.execution_context
                progress = result.get('current_step_index', 0) / max(result.get('total_steps', 1), 1)

            if task.status == TaskStatus.FAILED:
                error = result.get('error') if result else "Execution failed"

            return ExecutionResult(
                execution_id=execution_id,
                status=status,
                result=result,
                error=error,
                progress=progress
            )
        except Exception as e:
            logger.error(f"PlaybookService: Failed to get execution result for {execution_id}: {e}", exc_info=True)
            return None

    async def load_playbook_run(
        self,
        playbook_code: str,
        locale: str = "zh-TW",
        workspace_id: Optional[str] = None
    ) -> Optional["PlaybookRun"]:
        """
        Load playbook.run = playbook.md + playbook.json

        Args:
            playbook_code: Playbook code
            locale: Language locale (default: zh-TW)
            workspace_id: Workspace ID (optional, for priority: user > capability > system)

        Returns:
            PlaybookRun with both .md and .json components, or None if playbook.md not found
        """
        from backend.app.models.playbook import PlaybookRun

        playbook = await self.get_playbook(playbook_code, locale, workspace_id)
        if not playbook:
            logger.warning(f"playbook.md not found for {playbook_code}")
            return None

        playbook_json = PlaybookJsonLoader.load_playbook_json(playbook_code)

        return PlaybookRun(
            playbook=playbook,
            playbook_json=playbook_json
        )

