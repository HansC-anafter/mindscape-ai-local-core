"""Runtime delegate methods for the WorkflowOrchestrator facade."""

from typing import Any, Dict, Optional, Set

from backend.app.services.workflow.remote_route import (
    ensure_remote_tool_child_shell as workflow_ensure_remote_tool_child_shell,
    get_cloud_connector as workflow_get_cloud_connector,
    maybe_execute_tool_via_remote_route as workflow_maybe_execute_tool_via_remote_route,
    resolve_remote_tool_route as workflow_resolve_remote_tool_route,
    resolve_tool_model_route as workflow_resolve_tool_model_route,
)
from backend.app.services.workflow.playbook_finalization import (
    finalize_playbook_execution as workflow_finalize_playbook_execution,
)
from backend.app.services.workflow.playbook_runtime import (
    apply_execution_profile_registry_route as workflow_apply_execution_profile_registry_route,
    ensure_execution_sandbox as workflow_ensure_execution_sandbox,
    resolve_resume_checkpoint as workflow_resolve_resume_checkpoint,
    restore_checkpoint_state as workflow_restore_checkpoint_state,
)
from backend.app.services.workflow.step_dispatch import (
    execute_playbook_slot as workflow_execute_playbook_slot,
    resolve_tool_slot_to_tool_id as workflow_resolve_tool_slot_to_tool_id,
)
from backend.app.services.workflow.tool_execution import (
    execute_tool_step as workflow_execute_tool_step,
)


class WorkflowOrchestratorRuntimeMethods:
    """Runtime wrapper methods inherited by WorkflowOrchestrator."""

    def _get_cloud_connector(self):
        return workflow_get_cloud_connector()

    def _ensure_remote_tool_child_shell(self, **kwargs):
        return workflow_ensure_remote_tool_child_shell(**kwargs)

    def _resolve_remote_tool_route(
        self,
        playbook_inputs: Optional[Dict[str, Any]],
        *,
        step_id: str,
        tool_id: str,
    ) -> Optional[Dict[str, Any]]:
        return workflow_resolve_remote_tool_route(
            playbook_inputs,
            step_id=step_id,
            tool_id=tool_id,
        )

    def _resolve_tool_model_route(
        self,
        *,
        tool_id: str,
        playbook_inputs: Optional[Dict[str, Any]],
        remote_route: Optional[Dict[str, Any]] = None,
        execution_profile: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        return workflow_resolve_tool_model_route(
            tool_id=tool_id,
            playbook_inputs=playbook_inputs,
            remote_route=remote_route,
            execution_profile=execution_profile,
        )

    async def _maybe_execute_tool_via_remote_route(
        self,
        *,
        step_id: str,
        tool_id: str,
        tool_inputs: Dict[str, Any],
        playbook_inputs: Dict[str, Any],
        execution_id: Optional[str],
        workspace_id: Optional[str],
    ) -> tuple[bool, Any]:
        return await workflow_maybe_execute_tool_via_remote_route(
            step_id=step_id,
            tool_id=tool_id,
            tool_inputs=tool_inputs,
            playbook_inputs=playbook_inputs,
            execution_id=execution_id,
            workspace_id=workspace_id,
            get_cloud_connector_fn=self._get_cloud_connector,
            ensure_remote_tool_child_shell_fn=self._ensure_remote_tool_child_shell,
        )

    async def _resolve_tool_slot_to_tool_id(
        self,
        *,
        step: Any,
        workspace_id: Optional[str],
        project_id: Optional[str],
        playbook_inputs: Optional[Dict[str, Any]] = None,
    ) -> str:
        return await workflow_resolve_tool_slot_to_tool_id(
            step=step,
            store=self.store,
            workspace_id=workspace_id,
            project_id=project_id,
            playbook_inputs=playbook_inputs,
        )

    async def _execute_playbook_slot(
        self,
        *,
        step: Any,
        resolved_inputs: Dict[str, Any],
        execution_id: Optional[str],
        workspace_id: Optional[str],
        profile_id: Optional[str],
        project_id: Optional[str],
    ) -> Dict[str, Any]:
        previous_depth = getattr(self, "_playbook_slot_depth", 0)
        self._playbook_slot_depth = previous_depth + 1
        try:
            return await workflow_execute_playbook_slot(
                step=step,
                current_depth=previous_depth,
                resolved_inputs=resolved_inputs,
                execution_id=execution_id,
                workspace_id=workspace_id,
                profile_id=profile_id,
                project_id=project_id,
                load_playbook_json_fn=self.load_playbook_json,
                execute_playbook_steps_fn=self._execute_playbook_steps,
            )
        finally:
            self._playbook_slot_depth = previous_depth

    async def _execute_tool_step(
        self,
        *,
        step: Any,
        tool_id: str,
        resolved_inputs: Dict[str, Any],
        playbook_inputs: Dict[str, Any],
        playbook_json: Any,
        execution_id: Optional[str],
        workspace_id: Optional[str],
        profile_id: Optional[str],
    ) -> Any:
        return await workflow_execute_tool_step(
            step=step,
            tool_id=tool_id,
            resolved_inputs=resolved_inputs,
            playbook_inputs=playbook_inputs,
            execution_profile=getattr(playbook_json, "execution_profile", None),
            execution_id=execution_id,
            workspace_id=workspace_id,
            profile_id=profile_id,
            resolve_remote_tool_route_fn=self._resolve_remote_tool_route,
            resolve_tool_model_route_fn=self._resolve_tool_model_route,
            maybe_execute_tool_via_remote_route_fn=self._maybe_execute_tool_via_remote_route,
            execute_tool_fn=self.tool_executor.execute_tool,
        )

    def _resolve_resume_checkpoint(
        self,
        *,
        playbook_inputs: Dict[str, Any],
        execution_id: Optional[str],
        playbook_json: Any,
    ) -> Optional[Dict[str, Any]]:
        return workflow_resolve_resume_checkpoint(
            playbook_inputs=playbook_inputs,
            execution_id=execution_id,
            playbook_code=getattr(playbook_json, "playbook_code", None),
        )

    def _restore_checkpoint_state(
        self,
        *,
        playbook_inputs: Dict[str, Any],
        resume_checkpoint: Optional[Dict[str, Any]],
    ) -> tuple[Dict[str, Dict[str, Any]], Set[str]]:
        return workflow_restore_checkpoint_state(
            playbook_inputs=playbook_inputs,
            resume_checkpoint=resume_checkpoint,
        )

    def _apply_execution_profile_registry_route(
        self,
        *,
        playbook_json: Any,
        playbook_inputs: Dict[str, Any],
    ) -> Optional[str]:
        return workflow_apply_execution_profile_registry_route(
            playbook_json=playbook_json,
            playbook_inputs=playbook_inputs,
        )

    async def _ensure_execution_sandbox(
        self,
        *,
        playbook_json: Any,
        execution_id: Optional[str],
        workspace_id: Optional[str],
        project_id: Optional[str],
        resume_checkpoint: Optional[Dict[str, Any]],
    ) -> Optional[str]:
        return await workflow_ensure_execution_sandbox(
            store=self.store,
            playbook_json=playbook_json,
            execution_id=execution_id,
            workspace_id=workspace_id,
            project_id=project_id,
            resume_checkpoint=resume_checkpoint,
        )

    async def _finalize_playbook_execution(
        self,
        *,
        playbook_json: Any,
        playbook_inputs: Dict[str, Any],
        step_outputs: Dict[str, Dict[str, Any]],
        final_outputs: Dict[str, Any],
        execution_id: Optional[str],
        workspace_id: Optional[str],
        sandbox_id: Optional[str],
    ) -> Dict[str, Any]:
        return await workflow_finalize_playbook_execution(
            store=self.store,
            playbook_json=playbook_json,
            playbook_inputs=playbook_inputs,
            step_outputs=step_outputs,
            final_outputs=final_outputs,
            execution_id=execution_id,
            workspace_id=workspace_id,
            sandbox_id=sandbox_id,
        )
