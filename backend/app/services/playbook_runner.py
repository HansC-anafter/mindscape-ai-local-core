"""
Playbook Runner Service
Handles Playbook execution with real LLM-powered conversations
"""

from typing import Dict, List, Optional, Any

from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.playbook_service import PlaybookService
from backend.app.services.stores.tool_calls_store import ToolCallsStore
from backend.app.services.stores.stage_results_store import StageResultsStore
from backend.app.services.conversation.workflow_tracker import WorkflowTracker
from backend.app.services.playbook import (
    PlaybookConversationManager,
    PlaybookToolExecutor,
    ExecutionStateStore,
    StepEventRecorder,
    PlaybookLLMProviderManager,
    PlaybookTaskManager,
)
from backend.app.services.story_thread.context_injector import (
    StoryThreadContextInjector,
)
from backend.app.services.playbook_runner_core.continuation import (
    continue_playbook_execution as runner_continue_playbook_execution,
)
from backend.app.services.playbook_runner_core.start_execution import (
    start_playbook_execution as runner_start_playbook_execution,
)
from backend.app.services.playbook_runner_core.session_state import (
    cleanup_execution as runner_cleanup_execution,
    get_playbook_execution_result as runner_get_playbook_execution_result,
    list_active_execution_ids as runner_list_active_execution_ids,
)
from backend.app.services.playbook_runner_core.step_reset import (
    reset_current_step as runner_reset_current_step,
)
from backend.app.services.playbook_run_executor_admission import (
    prepare_playbook_admission,
)

class PlaybookRunner:
    """Main Playbook execution service"""

    def __init__(self, config_store=None):
        self.store = MindscapeStore()
        # Use PlaybookService instead of PlaybookLoader
        self.playbook_service = PlaybookService(store=config_store)
        # Import here to avoid circular dependency
        if config_store is None:
            from backend.app.services.config_store import ConfigStore

            config_store = ConfigStore()
        self.config_store = config_store
        self.llm_manager = None  # Will be initialized per-profile
        self.active_conversations: Dict[str, PlaybookConversationManager] = {}
        self.tool_calls_store = ToolCallsStore()
        self.stage_results_store = StageResultsStore()
        self.workflow_tracker = WorkflowTracker(self.store)
        # Initialize modular components
        self.tool_executor = PlaybookToolExecutor(self.store, self.workflow_tracker)
        self.state_store = ExecutionStateStore(self.store)
        self.step_recorder = StepEventRecorder(
            self.store, self.workflow_tracker, self.tool_calls_store, self.state_store
        )
        self.llm_provider_manager = PlaybookLLMProviderManager(self.config_store)
        self.task_manager = PlaybookTaskManager(self.store)
        self.context_injector = StoryThreadContextInjector()

    async def _run_tool(
        self,
        tool_fqn: str,
        profile_id: str = None,
        workspace_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        step_id: Optional[str] = None,
        factory_cluster: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """
        Unified tool execution entry point (delegates to PlaybookToolExecutor)

        This method provides a single entry point for all tool calls from Playbooks.
        It routes to capability package tools via registry, or falls back to legacy services.

        Args:
            tool_fqn: Fully qualified tool name (e.g., "major_proposal.import_template_from_files")
            profile_id: Profile ID (optional, for event recording)
            **kwargs: Parameters to pass to the tool

        Returns:
            Tool execution result
        """
        return await self.tool_executor.execute_tool(
            tool_fqn=tool_fqn,
            profile_id=profile_id,
            workspace_id=workspace_id,
            execution_id=execution_id,
            step_id=step_id,
            factory_cluster=factory_cluster,
            **kwargs,
        )

    async def start_playbook_execution(
        self,
        playbook_code: str,
        profile_id: str,
        inputs: Optional[Dict[str, Any]] = None,
        workspace_id: Optional[str] = None,
        project_id: Optional[str] = None,
        target_language: Optional[str] = None,
        variant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Start a new Playbook execution."""
        governed_inputs, snapshot = await prepare_playbook_admission(
            playbook_code=playbook_code,
            profile_id=profile_id,
            workspace_id=workspace_id,
            project_id=project_id,
            inputs=inputs,
        )
        if snapshot is not None:
            self.tool_executor.execution_context.update(
                {
                    "workspace_id": workspace_id,
                    "execution_admission_snapshot": snapshot.model_dump(
                        mode="json"
                    ),
                }
            )
        return await runner_start_playbook_execution(
            self,
            playbook_code=playbook_code,
            profile_id=profile_id,
            inputs=governed_inputs,
            workspace_id=workspace_id,
            project_id=project_id,
            target_language=target_language,
            variant_id=variant_id,
        )

    async def continue_playbook_execution(
        self, execution_id: str, user_message: str, profile_id: str = "default-user"
    ) -> Dict[str, Any]:
        """Continue an ongoing Playbook execution."""
        return await runner_continue_playbook_execution(
            self,
            execution_id=execution_id,
            user_message=user_message,
            profile_id=profile_id,
        )

    async def reset_current_step(
        self, execution_id: str, profile_id: str = "default-user"
    ) -> Dict[str, Any]:
        """Reset current step to restart from the beginning of current step."""
        return await runner_reset_current_step(
            self,
            execution_id=execution_id,
            profile_id=profile_id,
        )

    async def get_playbook_execution_result(
        self, execution_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get the final structured output from a completed execution"""
        return runner_get_playbook_execution_result(
            execution_id=execution_id,
            active_conversations=self.active_conversations,
        )

    def cleanup_execution(self, execution_id: str):
        """Clean up completed execution from memory"""
        runner_cleanup_execution(
            execution_id=execution_id,
            active_conversations=self.active_conversations,
        )

    def list_active_executions(self) -> List[str]:
        """List all active execution IDs"""
        return runner_list_active_execution_ids(self.active_conversations)
