"""
GovernanceEngine - Unified completion ingress for all playbook/task results.

Provides ``process_completion()`` as the single entry-point that all
result paths (workflow executor, REST endpoints, WebSocket message
handlers, webhook) should delegate to.

Internally it:
1.  Delegates onboarding-specific playbooks to ``MindscapeOnboardingService``
    for backward compatibility.
2.  Calls ``TaskResultLandingService.land_result()`` for durable persistence.
3.  Produces a post-landing provenance sidecar via ``PackDispatchAdapter``.
4.  Runs ``AcceptanceEvaluator`` and emits governance signals.
"""

import logging
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.governance_artifacts import (
    backfill_provenance as artifact_backfill_provenance,
    register_project_artifact,
    update_artifact_metadata,
)
from backend.app.services.orchestration.governance_completion import (
    process_completion as process_completion_helper,
)
from backend.app.services.orchestration.governance_follow_up import (
    backfill_eval_summary,
    calculate_acceptance_pass_rate,
    create_follow_up_task,
    resolve_acceptance_tests,
    resolve_governance_payload,
    sync_correctness_signals,
    trigger_follow_up,
)
from backend.app.services.orchestration.governance_remote_terminal import (
    process_remote_terminal_event as process_remote_terminal_event_helper,
)
from backend.app.services.orchestration.governance_webhook import (
    invoke_legacy_webhook_handler,
    process_playbook_webhook as process_playbook_webhook_helper,
)

logger = logging.getLogger(__name__)

ALLOWED_COMPLETION_INGRESS = (
    "playbook_runtime",
    "agent_rest_result",
    "agent_ws_result",
    "playbook_webhook",
)


class GovernanceEngine:
    """Unified completion ingress - single entry-point for result landing.

    All code paths that previously instantiated ``TaskResultLandingService``
    directly should instead call ``GovernanceEngine.process_completion()``.

    Current scope:
    - Transparently wraps the existing ``land_result`` flow.
    - Delegates onboarding-specific webhooks for backward compat.
    - Provides a stable API surface for acceptance evaluation,
      provenance tracking, and event emission.
    """

    def __init__(self, adapter: Any = None) -> None:
        # Lazy-load heavy dependencies to avoid import-time side effects
        self._landing: Any = None
        self._tasks_store: Any = None
        self._meeting_session_store: Any = None
        self._adapter = adapter

    # ------------------------------------------------------------------
    # Lazy accessors
    # ------------------------------------------------------------------

    @property
    def landing(self):
        if self._landing is None:
            from app.services.task_result_landing import TaskResultLandingService

            self._landing = TaskResultLandingService()
        return self._landing

    @property
    def tasks_store(self):
        if self._tasks_store is None:
            from backend.app.services.stores.tasks_store import TasksStore

            self._tasks_store = TasksStore()
        return self._tasks_store

    @property
    def meeting_session_store(self):
        if getattr(self, "_meeting_session_store", None) is None:
            from backend.app.services.stores.meeting_session_store import (
                MeetingSessionStore,
            )

            self._meeting_session_store = MeetingSessionStore()
        return self._meeting_session_store

    @property
    def adapter(self):
        """Lazily instantiate PackDispatchAdapter if not injected."""
        if self._adapter is None:
            try:
                from backend.app.services.orchestration.pack_dispatch_adapter import (
                    PackDispatchAdapter,
                )
                self._adapter = PackDispatchAdapter()
            except Exception as exc:
                logger.debug("GovernanceEngine: PackDispatchAdapter unavailable: %s", exc)
                self._adapter = False  # Sentinel: tried and failed
        return self._adapter if self._adapter is not False else None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def process_completion(
        self,
        *,
        workspace_id: str,
        execution_id: str,
        result_data: Dict[str, Any],
        storage_base_path: Optional[str] = None,
        artifacts_dirname: str = "artifacts",
        thread_id: Optional[str] = None,
        project_id: Optional[str] = None,
        task_id: Optional[str] = None,
        playbook_code: Optional[str] = None,
        defer_task_terminal_update: bool = False,
    ) -> Optional[Dict[str, Any]]:
        """Land execution results through a single governed entry point.

        This method replaces direct calls to
        ``TaskResultLandingService.land_result()`` scattered across the
        codebase. It wraps the same underlying logic while providing a
        hook surface for governance extensions.

        Returns:
            Landing result dict, or None on failure.
        """
        return process_completion_helper(
            self,
            workspace_id=workspace_id,
            execution_id=execution_id,
            result_data=result_data,
            storage_base_path=storage_base_path,
            artifacts_dirname=artifacts_dirname,
            thread_id=thread_id,
            project_id=project_id,
            task_id=task_id,
            playbook_code=playbook_code,
            defer_task_terminal_update=defer_task_terminal_update,
        )

    def process_remote_terminal_event(
        self,
        *,
        tenant_id: str,
        workspace_id: str,
        execution_id: str,
        trace_id: str,
        status: str,
        result_payload: Optional[Dict[str, Any]],
        error_message: Optional[str],
        job_type: Optional[str] = None,
        capability_code: Optional[str] = None,
        playbook_code: Optional[str] = None,
        provider_metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Handle remote terminal events and bridge success back to completion ingress."""
        return process_remote_terminal_event_helper(
            self,
            tenant_id=tenant_id,
            workspace_id=workspace_id,
            execution_id=execution_id,
            trace_id=trace_id,
            status=status,
            result_payload=result_payload,
            error_message=error_message,
            job_type=job_type,
            capability_code=capability_code,
            playbook_code=playbook_code,
            provider_metadata=provider_metadata,
        )

    async def process_playbook_webhook(
        self,
        *,
        execution_id: str,
        playbook_code: str,
        user_id: str,
        output_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle playbook completion webhooks.

        Backward-compatible wrapper:
        - Onboarding playbooks are delegated to ``MindscapeOnboardingService``.
        - Regular playbooks go through the standard ``process_completion``.
        """
        return await process_playbook_webhook_helper(
            self,
            execution_id=execution_id,
            playbook_code=playbook_code,
            user_id=user_id,
            output_data=output_data,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_playbook_code(self, execution_id: str) -> Optional[str]:
        """Auto-resolve playbook_code from task/execution context.

        This covers call sites (rest_endpoints, message_handlers) that
        don't pass playbook_code explicitly.
        """
        try:
            task = self.tasks_store.get_task_by_execution_id(execution_id)
            if task:
                # Try execution_context.playbook_code first
                ctx = getattr(task, "execution_context", None) or {}
                pb_code = ctx.get("playbook_code")
                if pb_code:
                    return pb_code
                # Try pack_id as fallback
                pack_id = getattr(task, "pack_id", None)
                if pack_id and pack_id not in ("meeting_dispatch", "meeting_projection"):
                    return pack_id
        except Exception as exc:
            logger.debug(
                "GovernanceEngine: playbook_code resolve failed for exec=%s: %s",
                execution_id,
                exc,
            )
        return None

    def _resolve_workspace_id(
        self,
        *,
        execution_id: str,
        output_data: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Resolve workspace_id from webhook payload or task context."""
        if isinstance(output_data, dict):
            workspace_id = output_data.get("workspace_id")
            if isinstance(workspace_id, str) and workspace_id:
                return workspace_id

        try:
            task = self.tasks_store.get_task_by_execution_id(execution_id)
            if task:
                ctx = getattr(task, "execution_context", None) or {}
                workspace_id = ctx.get("workspace_id") or getattr(task, "workspace_id", "")
                if isinstance(workspace_id, str):
                    return workspace_id
        except Exception as exc:
            logger.debug(
                "GovernanceEngine: workspace_id resolve failed for exec=%s: %s",
                execution_id,
                exc,
            )
        return ""

    def _resolve_project_id(
        self,
        *,
        execution_id: str,
        project_id: Optional[str] = None,
    ) -> Optional[str]:
        """Resolve project_id from explicit args or task context."""
        if isinstance(project_id, str) and project_id:
            return project_id

        try:
            task = self.tasks_store.get_task_by_execution_id(execution_id)
            if task:
                ctx = getattr(task, "execution_context", None) or {}
                resolved = (
                    getattr(task, "project_id", None)
                    or ctx.get("project_id")
                )
                if isinstance(resolved, str) and resolved:
                    return resolved
        except Exception as exc:
            logger.debug(
                "GovernanceEngine: project_id resolve failed for exec=%s: %s",
                execution_id,
                exc,
            )
        return None

    async def _invoke_legacy_webhook_handler(
        self,
        *,
        execution_id: str,
        playbook_code: str,
        user_id: str,
        output_data: Dict[str, Any],
        hook: str,
    ) -> Dict[str, Any]:
        """Invoke legacy webhook hooks behind a single adapter boundary."""
        return await invoke_legacy_webhook_handler(
            execution_id=execution_id,
            playbook_code=playbook_code,
            user_id=user_id,
            output_data=output_data,
            hook=hook,
        )

    def _register_project_artifact(
        self,
        *,
        project_id: str,
        artifact_id: str,
        artifact_path: str,
        artifact_type: str,
        created_by: str,
    ):
        """Register landed artifacts in the project-scoped artifact registry."""
        return register_project_artifact(
            project_id=project_id,
            artifact_id=artifact_id,
            artifact_path=artifact_path,
            artifact_type=artifact_type,
            created_by=created_by,
        )

    def _update_artifact_metadata(
        self,
        *,
        artifact_id: str,
        updater,
    ) -> bool:
        """Load artifact metadata, apply update, and persist it."""
        return update_artifact_metadata(
            artifact_id=artifact_id,
            updater=updater,
        )

    def _backfill_provenance(
        self,
        *,
        artifact_id: str,
        execution_id: str,
        playbook_code: Optional[str],
        parsed_output: Dict[str, Any],
    ) -> None:
        """Persist provenance sidecar into artifact metadata (non-fatal).

        Steps:
        1.  GET artifact to read existing metadata
        2.  Deep merge ``parsed_output`` into ``metadata.provenance``
        3.  PUT updated metadata back via ``update_artifact``
        4.  Mark handoff_registry entries as completed

        All errors are logged and swallowed; backfill must never
        break the completion flow.
        """
        artifact_backfill_provenance(
            self,
            artifact_id=artifact_id,
            execution_id=execution_id,
            playbook_code=playbook_code,
            parsed_output=parsed_output,
        )

    def _resolve_acceptance_tests(self, execution_id: str) -> Optional[List[str]]:
        """Resolve acceptance_tests from the task's GovernanceContext.

        Returns the list of acceptance test strings, or None if not
        available.
        """
        return resolve_acceptance_tests(self, execution_id)

    def _resolve_governance_payload(self, execution_id: str) -> Optional[Dict[str, Any]]:
        """Resolve governance payload from top-level, nested metadata, or inputs."""
        return resolve_governance_payload(self, execution_id)

    @staticmethod
    def _calculate_acceptance_pass_rate(eval_summary: Dict[str, Any]) -> float:
        """Compute pass rate across explicit acceptance checks only."""
        return calculate_acceptance_pass_rate(eval_summary)

    def _sync_correctness_signals(
        self,
        *,
        execution_id: str,
        artifact_id: Optional[str],
        playbook_code: Optional[str],
        eval_summary: Dict[str, Any],
        remediation: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Mirror latest correctness signals into meeting session metadata.

        Artifact metadata provenance remains the SSOT. Session metadata stores
        the latest normalized correctness summary so the next MeetingEngine
        dispatch can read it without scanning artifacts.
        """
        return sync_correctness_signals(
            self,
            execution_id=execution_id,
            artifact_id=artifact_id,
            playbook_code=playbook_code,
            eval_summary=eval_summary,
            remediation=remediation,
        )

    def _backfill_eval_summary(
        self,
        *,
        artifact_id: str,
        eval_summary: Dict[str, Any],
    ) -> None:
        """Persist eval_summary into artifact.metadata.provenance (non-fatal).

        Uses the same GET-merge-PUT pattern as _backfill_provenance.
        """
        backfill_eval_summary(
            self,
            artifact_id=artifact_id,
            eval_summary=eval_summary,
        )

    def _trigger_follow_up(
        self,
        *,
        workspace_id: str,
        execution_id: str,
        artifact_id: Optional[str],
        playbook_code: Optional[str],
        eval_result: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """Evaluate remediation policy and create follow-up task if warranted.

        Returns the remediation decision dict, or None.
        """
        return trigger_follow_up(
            self,
            workspace_id=workspace_id,
            execution_id=execution_id,
            artifact_id=artifact_id,
            playbook_code=playbook_code,
            eval_result=eval_result,
        )

    def _create_follow_up_task(
        self,
        *,
        workspace_id: str,
        playbook_code: Optional[str],
        follow_up_context: Dict[str, Any],
    ) -> None:
        """Create a follow-up task carrying remediation context.

        Uses TasksStore.create_task() which auto-enqueues to Redis.
        Idempotency is guarded by HandoffRegistryStore.
        """
        create_follow_up_task(
            self,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            follow_up_context=follow_up_context,
        )
