"""
Workspace Agent Executor

Bridge between Workspace tasks and External Agent adapters.
Handles context injection, governance checks, and execution tracing.
"""

import logging
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

from backend.app.services.external_agents.core.registry import get_agent_registry
from backend.app.services.external_agents.core.base_adapter import (
    AgentRequest,
    AgentResponse,
)
from backend.app.services.external_agents.core.execution_trace import (
    ExecutionTraceService,
    ExecutionTrace,
)
from backend.app.services.governance.playbook_preflight import PlaybookPreflight
from backend.app.services.governance.stubs import PreflightStatus

logger = logging.getLogger(__name__)


@dataclass
class AgentExecutionRequest:
    """Request for external agent execution"""

    task: str
    workspace_id: str
    agent_id: str
    sandbox_path: str
    context: Dict[str, Any] = field(default_factory=dict)
    allowed_tools: List[str] = field(default_factory=list)
    timeout_seconds: int = 300
    trace_id: Optional[str] = None


@dataclass
class AgentExecutionResponse:
    """Response from external agent execution"""

    success: bool
    output: str
    artifacts: List[str] = field(default_factory=list)
    error: Optional[str] = None
    trace_id: Optional[str] = None
    execution_time_seconds: float = 0.0
    risk_level: str = "low"


class WorkspaceAgentExecutor:
    """
    Workspace Agent Executor

    Responsibilities:
    1. Receive tasks approved by UnifiedDecisionCoordinator
    2. Inject Workspace context (CoreMemory + RuntimeProfile)
    3. Execute External Agent in sandbox
    4. Record ExecutionTrace
    """

    def __init__(self, workspace: Any):
        """
        Initialize executor for a specific workspace.

        Args:
            workspace: Workspace model instance
        """
        self.workspace = workspace
        self.registry = get_agent_registry()
        self.preflight = PlaybookPreflight()
        self.trace_service = ExecutionTraceService()

    async def check_agent_available(self, agent_id: Optional[str] = None) -> bool:
        """
        Check if the specified agent runtime is currently connected.

        Args:
            agent_id: Agent to check (default: workspace.preferred_agent)

        Returns:
            True if the agent runtime is connected and available
        """
        agent_id = agent_id or getattr(self.workspace, "preferred_agent", None)
        if not agent_id:
            return False

        try:
            from backend.app.services.external_agents.core.registry import (
                get_agent_registry,
            )

            registry = get_agent_registry()
            adapter = registry.get_adapter(agent_id)
            if not adapter:
                logger.debug(f"No adapter found for agent {agent_id}")
                return False

            return await adapter.is_available()
        except Exception as e:
            logger.warning(f"Failed to check agent availability: {e}")
            return False

    async def execute(
        self,
        task: str,
        agent_id: Optional[str] = None,
        skip_preflight: bool = False,
        context_overrides: Optional[Dict[str, Any]] = None,
    ) -> AgentExecutionResponse:
        """
        Execute a task via external agent.

        Args:
            task: Task description
            agent_id: Override agent ID (default: workspace.preferred_agent)
            skip_preflight: Skip preflight checks (for pre-approved tasks)
            context_overrides: Override context values

        Returns:
            AgentExecutionResponse with results
        """
        start_time = _utc_now()
        agent_id = agent_id or self.workspace.preferred_agent

        if not agent_id:
            return AgentExecutionResponse(
                success=False,
                output="",
                error="No agent specified and workspace has no preferred_agent",
            )

        # 1. Preflight check (unless skipped)
        if not skip_preflight:
            preflight_result = await self.preflight.check_external_agent_execution(
                agent_id=agent_id,
                task=task,
                workspace=self.workspace,
            )

            if not preflight_result.accepted:
                if preflight_result.status == PreflightStatus.NEED_CLARIFICATION:
                    return AgentExecutionResponse(
                        success=False,
                        output="",
                        error=f"Requires clarification: {preflight_result.clarification_questions}",
                    )
                else:
                    return AgentExecutionResponse(
                        success=False,
                        output="",
                        error=f"Preflight rejected: {preflight_result.rejection_reason}",
                    )

        # 2. Get adapter
        adapter = self.registry.get_adapter(agent_id)
        if not adapter:
            return AgentExecutionResponse(
                success=False,
                output="",
                error=f"Agent adapter not found: {agent_id}",
            )

        # 3. Build context
        context = await self._build_context()
        if context_overrides:
            context.update(context_overrides)

        # 4. Get sandbox path
        sandbox_path = self._get_sandbox_path()

        # 5. Create request
        request = AgentExecutionRequest(
            task=task,
            workspace_id=self.workspace.id,
            agent_id=agent_id,
            sandbox_path=sandbox_path,
            context=context,
            timeout_seconds=self._get_timeout(),
        )

        # 6. Start trace
        trace = self.trace_service.start_trace(
            workspace_id=self.workspace.id,
            agent_id=agent_id,
            task=task,
        )

        # 7. Execute
        try:
            logger.info(
                f"Executing task via {agent_id}: workspace={self.workspace.id}, "
                f"sandbox={sandbox_path}"
            )

            agent_request = AgentRequest(
                task=task,
                sandbox_path=sandbox_path,
                workspace_id=self.workspace.id,
                max_duration_seconds=request.timeout_seconds,
                agent_config=context,
            )

            result = await adapter.execute(agent_request)

            # 8. Complete trace
            execution_time = (_utc_now() - start_time).total_seconds()
            result_artifacts = result.files_created + result.files_modified
            trace.complete(
                success=result.success,
                output=result.output,
                artifacts=result_artifacts,
            )

            return AgentExecutionResponse(
                success=result.success,
                output=result.output,
                error=result.error,
                artifacts=result_artifacts,
                trace_id=trace.trace_id,
                execution_time_seconds=execution_time,
            )

        except Exception as e:
            logger.error(f"Agent execution failed: {e}", exc_info=True)
            execution_time = (_utc_now() - start_time).total_seconds()
            trace.fail(str(e))

            return AgentExecutionResponse(
                success=False,
                output="",
                error=str(e),
                trace_id=trace.trace_id,
                execution_time_seconds=execution_time,
            )

    async def _build_context(self) -> Dict[str, Any]:
        """
        Build execution context from WorkspaceCoreMemory + RuntimeProfile.

        Returns:
            Context dictionary to inject into agent prompt
        """
        context = {}

        # 1. Core Memory (brand identity, style)
        try:
            from backend.app.services.memory.workspace_core_memory import (
                WorkspaceCoreMemoryService,
            )

            memory_service = WorkspaceCoreMemoryService()
            core_memory = await memory_service.get_core_memory(self.workspace.id)

            if core_memory:
                context["brand_identity"] = core_memory.brand_identity
                context["voice_and_tone"] = core_memory.voice_and_tone
                context["style_constraints"] = core_memory.style_constraints
                context["custom_instructions"] = core_memory.custom_instructions

        except Exception as e:
            logger.warning(f"Failed to load core memory: {e}")

        # 2. Runtime Profile constraints
        try:
            # Get from workspace metadata or runtime_profile
            runtime_profile = getattr(self.workspace, "runtime_profile", None)
            if runtime_profile:
                if hasattr(runtime_profile, "tool_policy"):
                    context["tool_policy"] = {
                        "allowlist": runtime_profile.tool_policy.allowlist,
                        "denylist": runtime_profile.tool_policy.denylist,
                    }
                if hasattr(runtime_profile, "loop_budget"):
                    context["loop_budget"] = {
                        "max_iterations": runtime_profile.loop_budget.max_iterations,
                        "timeout_seconds": runtime_profile.loop_budget.timeout_seconds,
                    }

        except Exception as e:
            logger.warning(f"Failed to load runtime profile: {e}")

        # 3. Sandbox config constraints
        sandbox_config = getattr(self.workspace, "sandbox_config", None) or {}
        context["sandbox_constraints"] = {
            "filesystem_scope": sandbox_config.get(
                "filesystem_scope", ["workspace/sandbox/*"]
            ),
            "network_allowlist": sandbox_config.get("network_allowlist", []),
            "max_execution_time": sandbox_config.get("max_execution_time_seconds", 300),
        }

        return context

    def _get_sandbox_path(self) -> str:
        """Get the sandbox path for this workspace."""
        # Use workspace storage_base_path + sandbox subdirectory
        base_path = getattr(self.workspace, "storage_base_path", None)
        if base_path:
            return f"{base_path}/sandbox"

        # Fallback to workspace ID based path
        return f"/tmp/mindscape/workspaces/{self.workspace.id}/sandbox"

    def _get_timeout(self) -> int:
        """Get execution timeout from sandbox config."""
        sandbox_config = getattr(self.workspace, "sandbox_config", None) or {}
        return sandbox_config.get("max_execution_time_seconds", 300)


async def get_workspace_agent_executor(
    workspace_id: str,
) -> Optional[WorkspaceAgentExecutor]:
    """
    Factory function to create WorkspaceAgentExecutor.

    Args:
        workspace_id: Workspace ID

    Returns:
        WorkspaceAgentExecutor instance or None if workspace not found
    """
    try:
        from backend.app.services.mindscape_store import MindscapeStore

        store = MindscapeStore()
        workspace = await store.get_workspace(workspace_id)

        if not workspace:
            logger.warning(f"Workspace not found: {workspace_id}")
            return None

        return WorkspaceAgentExecutor(workspace)

    except Exception as e:
        logger.error(f"Failed to create WorkspaceAgentExecutor: {e}", exc_info=True)
        return None
