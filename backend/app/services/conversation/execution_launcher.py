"""
Execution Launcher

Launches playbook execution via PlaybookService or PlaybookRunExecutor
and handles execution results.
"""

import logging
import uuid
from typing import Dict, Any, Optional

from ...core.domain_context import LocalDomainContext
from ...models.playbook import (
    PlaybookInvocationContext,
    InvocationMode,
    InvocationStrategy,
    InvocationTolerance,
    PlanContext
)

logger = logging.getLogger(__name__)


class ExecutionLauncher:
    """
    Launches playbook execution

    Responsibilities:
    - Call playbook_service.execute_playbook or playbook_run_executor.execute_playbook_run
    - Ensure inputs contain project_id/name if needed
    - Handle execution result and missing execution_id warnings
    - Support both PlaybookService (unified) and PlaybookRunExecutor (backward compatibility)
    """

    def __init__(
        self,
        playbook_service=None,
        playbook_run_executor=None,
        default_locale: str = "en",
    ):
        """
        Initialize ExecutionLauncher

        Args:
            playbook_service: Optional PlaybookService instance (for unified query)
            playbook_run_executor: PlaybookRunExecutor instance (for backward compatibility)
            default_locale: Default locale for i18n
        """
        self.playbook_service = playbook_service
        self.playbook_run_executor = playbook_run_executor
        self.default_locale = default_locale

    async def launch(
        self,
        playbook_code: str,
        inputs: Dict[str, Any],
        ctx: LocalDomainContext,
        project_meta: Optional[Dict[str, Any]] = None,
        project_id: Optional[str] = None,
        plan_id: Optional[str] = None,
        task_id: Optional[str] = None,
        plan_context: Optional[PlanContext] = None,
        trace_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Launch playbook execution

        Args:
            playbook_code: Playbook code to execute
            inputs: Playbook inputs
            ctx: Execution context
            project_meta: Optional project metadata
            project_id: Optional project ID
            plan_id: Optional plan ID (for plan_node mode)
            task_id: Optional task ID (for plan_node mode)
            plan_context: Optional plan context (for plan_node mode)
            trace_id: Optional trace ID for tracking

        Returns:
            Dict with execution_id, execution_mode, and raw_result
        """
        # Ensure project metadata is included in inputs
        inputs = self._ensure_project_metadata(inputs, project_meta)

        # Ensure workspace_id and profile_id are set
        inputs["workspace_id"] = ctx.workspace_id

        # Create invocation context
        invocation_context = self._create_invocation_context(
            plan_id=plan_id,
            task_id=task_id,
            plan_context=plan_context,
            trace_id=trace_id or str(uuid.uuid4()),
        )

        # Launch execution
        try:
            if self.playbook_service:
                execution_result = await self._launch_via_playbook_service(
                    playbook_code=playbook_code,
                    inputs=inputs,
                    ctx=ctx,
                    context=invocation_context,
                )
            else:
                execution_result = await self._launch_via_run_executor(
                    playbook_code=playbook_code,
                    inputs=inputs,
                    ctx=ctx,
                    project_id=project_id,
                    context=invocation_context,
                )

            # Handle execution result
            return self._handle_execution_result(
                playbook_code=playbook_code,
                execution_result=execution_result,
            )

        except Exception as e:
            logger.error(
                f"Failed to launch playbook execution for {playbook_code}: {e}",
                exc_info=True,
            )
            raise

    def _create_invocation_context(
        self,
        plan_id: Optional[str] = None,
        task_id: Optional[str] = None,
        plan_context: Optional[PlanContext] = None,
        trace_id: Optional[str] = None,
    ) -> Optional[PlaybookInvocationContext]:
        """
        Create invocation context based on execution mode

        Args:
            plan_id: Optional plan ID
            task_id: Optional task ID
            plan_context: Optional plan context
            trace_id: Optional trace ID

        Returns:
            PlaybookInvocationContext or None (for legacy behavior)
        """
        if plan_id:
            return PlaybookInvocationContext(
                mode=InvocationMode.PLAN_NODE,
                plan_id=plan_id,
                task_id=task_id,
                plan_context=plan_context,
                strategy=InvocationStrategy(
                    max_lookup_rounds=1,
                    allow_spawn_new_tasks=False,
                    allow_expansion=False,
                    wait_for_upstream_tasks=True,
                    tolerance=InvocationTolerance.STRICT,
                ),
                trace_id=trace_id or str(uuid.uuid4()),
            )
        return PlaybookInvocationContext(
            mode=InvocationMode.STANDALONE,
            strategy=InvocationStrategy(
                max_lookup_rounds=3,
                allow_spawn_new_tasks=False,
                allow_expansion=False,
                wait_for_upstream_tasks=False,
                tolerance=InvocationTolerance.ADAPTIVE,
            ),
            trace_id=trace_id or str(uuid.uuid4()),
        )

    async def _launch_via_playbook_service(
        self,
        playbook_code: str,
        inputs: Dict[str, Any],
        ctx: LocalDomainContext,
        context: Optional[PlaybookInvocationContext] = None,
    ) -> Dict[str, Any]:
        """
        Launch execution via PlaybookService

        Args:
            playbook_code: Playbook code
            inputs: Playbook inputs
            ctx: Execution context
            context: Optional invocation context

        Returns:
            Execution result dict
        """
        from ...services.playbook_service import ExecutionMode as PlaybookExecutionMode

        execution_result_obj = await self.playbook_service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id=ctx.workspace_id,
            profile_id=ctx.actor_id,
            inputs=inputs,
            execution_mode=PlaybookExecutionMode.ASYNC,
            locale=self.default_locale,
            context=context,
        )

        # Convert ExecutionResult to dict format
        return {
            "execution_id": execution_result_obj.execution_id,
            "execution_mode": (
                "workflow"
                if execution_result_obj.status == "running"
                else "conversation"
            ),
            "result": execution_result_obj.result or {},
        }

    async def _launch_via_run_executor(
        self,
        playbook_code: str,
        inputs: Dict[str, Any],
        ctx: LocalDomainContext,
        project_id: Optional[str],
        context: Optional[PlaybookInvocationContext] = None,
    ) -> Dict[str, Any]:
        """
        Launch execution via PlaybookRunExecutor (backward compatibility)

        Args:
            playbook_code: Playbook code
            inputs: Playbook inputs
            ctx: Execution context
            project_id: Optional project ID
            context: Optional invocation context

        Returns:
            Execution result dict
        """
        return await self.playbook_run_executor.execute_playbook_run(
            playbook_code=playbook_code,
            profile_id=ctx.actor_id,
            inputs=inputs,
            workspace_id=ctx.workspace_id,
            project_id=project_id,
            locale=self.default_locale,
            context=context,
        )

    def _ensure_project_metadata(
        self,
        inputs: Dict[str, Any],
        project_meta: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Ensure inputs contain project_id/name if project_meta is available

        Args:
            inputs: Playbook inputs
            project_meta: Optional project metadata

        Returns:
            Updated inputs with project metadata
        """
        if not project_meta:
            return inputs

        # Add project_id if not already present
        if "project_id" not in inputs and project_meta.get("id"):
            inputs["project_id"] = project_meta["id"]

        # Add project_name if available and not already present
        if "project_name" not in inputs and project_meta.get("name"):
            inputs["project_name"] = project_meta["name"]

        # Add project_title if available and not already present
        if "project_title" not in inputs and project_meta.get("title"):
            inputs["project_title"] = project_meta["title"]

        return inputs

    def _handle_execution_result(
        self,
        playbook_code: str,
        execution_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Handle execution result and check for missing execution_id

        Args:
            playbook_code: Playbook code
            execution_result: Execution result from playbook service/executor

        Returns:
            Dict with execution_id, execution_mode, and raw_result
        """
        if not execution_result:
            logger.warning(
                f"Playbook {playbook_code} execution returned None result"
            )
            return {
                "execution_id": None,
                "execution_mode": "conversation",
                "raw_result": None,
            }

        execution_id = execution_result.get("execution_id")
        execution_mode = execution_result.get("execution_mode", "conversation")

        if execution_id:
            logger.info(
                f"Playbook {playbook_code} started successfully, execution_id={execution_id}, mode={execution_mode}"
            )
        else:
            logger.warning(
                f"Playbook {playbook_code} started but no execution_id returned. "
                f"Result: {execution_result}"
            )

        return {
            "execution_id": execution_id,
            "execution_mode": execution_mode,
            "raw_result": execution_result,
        }
