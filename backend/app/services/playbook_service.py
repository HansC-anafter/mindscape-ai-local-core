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

    def __init__(self, store=None, cloud_client=None, cloud_extension_manager=None):
        """
        Initialize PlaybookService

        Args:
            store: MindscapeStore instance (optional, for user playbooks and state management)
            cloud_client: CloudPlaybookClient instance (optional, deprecated - use cloud_extension_manager)
            cloud_extension_manager: CloudExtensionManager instance (optional, for cloud playbooks from multiple providers)
        """
        self.store = store

        # Support both old cloud_client and new cloud_extension_manager for backward compatibility
        if cloud_extension_manager:
            self.cloud_extension_manager = cloud_extension_manager
        elif cloud_client:
            # Legacy support: wrap old cloud_client in extension manager
            from ...services.cloud_extension_manager import CloudExtensionManager
            from ...services.cloud_providers.official import OfficialCloudProvider

            self.cloud_extension_manager = CloudExtensionManager.instance()
            # Create a provider wrapper for the old client
            # This is a temporary bridge for backward compatibility
            logger.warning("Using deprecated cloud_client parameter. Please migrate to cloud_extension_manager.")
        else:
            self.cloud_extension_manager = None

        self.registry = PlaybookRegistry(store, cloud_extension_manager=self.cloud_extension_manager)

    async def get_playbook(
        self,
        playbook_code: str,
        locale: str = "zh-TW",
        workspace_id: Optional[str] = None,
        runtime_tier: Optional[str] = None,
    ) -> Optional[Playbook]:
        """
        Get playbook details

        Args:
            playbook_code: Playbook code
            locale: Language locale (default: zh-TW)
            workspace_id: Workspace ID (optional, for priority: user > capability > system)
            runtime_tier: Runtime tier filter (optional, "local", "cloud_recommended", "cloud_only")

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

        # Check runtime_tier compatibility if specified
        if playbook and runtime_tier:
            playbook_runtime_tier = getattr(playbook.metadata, 'runtime_tier', None)
            if playbook_runtime_tier == "cloud_only" and runtime_tier == "local":
                logger.warning(f"Playbook {playbook_code} requires cloud execution but local was requested")
                return None  # Cloud-only playbook not available for local execution

        return playbook

    async def list_playbooks(
        self,
        workspace_id: Optional[str] = None,
        locale: Optional[str] = None,
        category: Optional[str] = None,
        source: Optional[PlaybookSource] = None,
        tags: Optional[List[str]] = None,
        runtime_tier: Optional[str] = None,
    ) -> List[PlaybookMetadata]:
        """
        List all available playbooks

        Args:
            workspace_id: Workspace ID (optional)
            locale: Language locale (optional)
            category: Category filter (optional)
            source: Source filter (system, capability, user)
            tags: Tags filter (optional, for P1.5 attribute mapping)
            runtime_tier: Runtime tier filter (optional, "local", "cloud_recommended", "cloud_only")

        Returns:
            List of playbook metadata
        """
        playbooks = await self.registry.list_playbooks(
            workspace_id=workspace_id,
            locale=locale,
            category=category,
            source=source,
            tags=tags
        )

        # Filter by runtime_tier if specified
        if runtime_tier:
            filtered_playbooks = []
            for playbook in playbooks:
                playbook_runtime_tier = getattr(playbook, 'runtime_tier', None)
                if runtime_tier == "local":
                    # Local execution: exclude cloud_only playbooks
                    if playbook_runtime_tier != "cloud_only":
                        filtered_playbooks.append(playbook)
                elif runtime_tier == "cloud_recommended":
                    # Cloud recommended: include all playbooks
                    filtered_playbooks.append(playbook)
                elif runtime_tier == "cloud_only":
                    # Cloud only: only include cloud_only playbooks
                    if playbook_runtime_tier == "cloud_only":
                        filtered_playbooks.append(playbook)
            return filtered_playbooks

        return playbooks

    async def fork_playbook(
        self,
        source_playbook_code: str,
        target_playbook_code: str,
        workspace_id: str,
        profile_id: str,
        locale: str = "zh-TW"
    ) -> Optional[Playbook]:
        """
        Fork a playbook from template to workspace instance

        Creates a workspace-scoped copy of a template playbook (system/tenant/profile).
        The forked playbook can be fully edited (SOP, resources, etc.).

        Args:
            source_playbook_code: Source playbook code (template)
            target_playbook_code: Target playbook code (new instance)
            workspace_id: Workspace ID for the new instance
            profile_id: Profile ID (owner)
            locale: Language locale

        Returns:
            Forked Playbook instance or None if failed
        """
        try:
            # Get source playbook
            source_playbook = await self.get_playbook(source_playbook_code, locale, workspace_id)
            if not source_playbook:
                logger.error(f"Source playbook not found: {source_playbook_code}")
                return None

            # Check if source is a template
            if not source_playbook.metadata.is_template():
                logger.warning(
                    f"Cannot fork non-template playbook: {source_playbook_code} "
                    f"(scope: {source_playbook.metadata.get_scope_level()})"
                )
                return None

            # Create new playbook metadata with workspace scope
            new_metadata = PlaybookMetadata(
                playbook_code=target_playbook_code,
                version=source_playbook.metadata.version,
                locale=locale,
                name=f"{source_playbook.metadata.name} (Fork)",
                description=source_playbook.metadata.description,
                tags=source_playbook.metadata.tags.copy(),
                language_strategy=source_playbook.metadata.language_strategy,
                supports_execution_chat=source_playbook.metadata.supports_execution_chat,
                discussion_agent=source_playbook.metadata.discussion_agent,
                supported_locales=source_playbook.metadata.supported_locales.copy(),
                default_locale=source_playbook.metadata.default_locale,
                auto_localize=source_playbook.metadata.auto_localize,
                entry_agent_type=source_playbook.metadata.entry_agent_type,
                onboarding_task=source_playbook.metadata.onboarding_task,
                icon=source_playbook.metadata.icon,
                required_tools=source_playbook.metadata.required_tools.copy(),
                tool_dependencies=source_playbook.metadata.tool_dependencies.copy(),
                background=source_playbook.metadata.background,
                optional_tools=source_playbook.metadata.optional_tools.copy(),
                kind=source_playbook.metadata.kind,
                interaction_mode=source_playbook.metadata.interaction_mode.copy(),
                visible_in=source_playbook.metadata.visible_in.copy(),
                # Set scope to workspace (instance)
                scope={"visibility": "workspace", "editable": True},
                owner={"type": "workspace", "workspace_id": workspace_id, "profile_id": profile_id},
                runtime_handler=source_playbook.metadata.runtime_handler,
                runtime_tier=source_playbook.metadata.runtime_tier,
                runtime=source_playbook.metadata.runtime,
            )

            # Create forked playbook
            forked_playbook = Playbook(
                metadata=new_metadata,
                sop_content=source_playbook.sop_content,
                user_notes=f"Forked from {source_playbook_code}"
            )

            # Save forked playbook to database (user playbooks)
            if self.store:
                from backend.app.services.playbook_loaders.database_loader import PlaybookDatabaseLoader
                # TODO: Implement save_playbook in PlaybookDatabaseLoader
                # For now, we'll need to add this functionality
                logger.info(
                    f"Forked playbook {source_playbook_code} -> {target_playbook_code} "
                    f"for workspace {workspace_id}"
                )

            # Invalidate cache
            self.registry.invalidate_cache(target_playbook_code, locale)

            return forked_playbook

        except Exception as e:
            logger.error(f"Failed to fork playbook {source_playbook_code}: {e}", exc_info=True)
            return None

    def validate_edit_permission(
        self,
        playbook: Playbook,
        edit_type: str = "sop"
    ) -> tuple[bool, Optional[str]]:
        """
        Validate if a playbook can be edited

        Template playbooks (system/tenant/profile) cannot have their SOP edited directly.
        Only workspace-scoped instances can be fully edited.

        Args:
            playbook: Playbook to validate
            edit_type: Type of edit ("sop", "metadata", "resources")

        Returns:
            (is_allowed, error_message)
        """
        if not playbook:
            return False, "Playbook not found"

        # Check if it's a template
        if playbook.metadata.is_template():
            if edit_type == "sop":
                return False, (
                    f"Cannot edit SOP for template playbook. "
                    f"Please fork to workspace first (scope: {playbook.metadata.get_scope_level()})"
                )
            elif edit_type == "resources":
                return False, (
                    f"Cannot edit resources for template playbook. "
                    f"Please fork to workspace first (scope: {playbook.metadata.get_scope_level()})"
                )
            # Metadata (name, description, tags) can be edited via overlay
            return True, None

        # Workspace instances can be fully edited
        return True, None

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

            # Extract execution_id from different possible locations
            execution_id = (
                execution_result_dict.get('execution_id') or
                execution_result_dict.get('result', {}).get('execution_id') if isinstance(execution_result_dict.get('result'), dict) else None
            )
            if not execution_id:
                import uuid
                execution_id = str(uuid.uuid4())
                logger.warning(f"PlaybookService: No execution_id found in result, generated new one: {execution_id}")
            else:
                logger.info(f"PlaybookService: Extracted execution_id={execution_id} from result")

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

