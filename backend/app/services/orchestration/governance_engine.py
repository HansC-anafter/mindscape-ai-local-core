"""
GovernanceEngine — Unified completion ingress for all playbook/task results.

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
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.services.orchestration.governance_follow_up import (
    backfill_eval_summary,
    calculate_acceptance_pass_rate,
    create_follow_up_task,
    resolve_acceptance_tests,
    resolve_governance_payload,
    sync_correctness_signals,
    trigger_follow_up,
)

logger = logging.getLogger(__name__)

ALLOWED_COMPLETION_INGRESS = (
    "playbook_runtime",
    "agent_rest_result",
    "agent_ws_result",
    "playbook_webhook",
)


class GovernanceEngine:
    """Unified completion ingress — single entry-point for result landing.

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
    ) -> Optional[Dict[str, Any]]:
        """Land execution results through a single governed entry point.

        This method replaces direct calls to
        ``TaskResultLandingService.land_result()`` scattered across the
        codebase. It wraps the same underlying logic while providing a
        hook surface for governance extensions.

        Returns:
            Landing result dict, or None on failure.
        """
        # --- Auto-resolve playbook_code from task context if not provided ---
        if not playbook_code:
            playbook_code = self._resolve_playbook_code(execution_id)

        logger.info(
            "GovernanceEngine.process_completion: exec=%s pb=%s ws=%s",
            execution_id,
            playbook_code or "(unknown)",
            workspace_id,
        )

        # Delegate to the existing landing service with the raw payload.
        landing_result = self.landing.land_result(
            workspace_id=workspace_id,
            execution_id=execution_id,
            result_data=result_data,
            storage_base_path=storage_base_path,
            artifacts_dirname=artifacts_dirname,
            thread_id=thread_id,
            project_id=project_id,
            task_id=task_id,
        )

        if landing_result:
            logger.info(
                "GovernanceEngine: landing succeeded exec=%s artifact=%s",
                execution_id,
                getattr(landing_result, "artifact_id", None),
            )
        else:
            logger.warning(
                "GovernanceEngine: landing returned None exec=%s",
                execution_id,
            )

        # Build the post-landing provenance sidecar.
        parsed_output = None
        if self.adapter and playbook_code:
            try:
                parsed_output = self.adapter.parse_result(
                    result_data=result_data,
                    playbook_code=playbook_code,
                )
            except Exception as exc:
                logger.warning(
                    "GovernanceEngine: parse_result sidecar failed (non-fatal): %s",
                    exc,
                )

        # Backfill provenance onto the landed artifact when available.
        artifact_id = getattr(landing_result, "artifact_id", None) if landing_result else None
        if parsed_output and artifact_id:
            self._backfill_provenance(
                artifact_id=artifact_id,
                execution_id=execution_id,
                playbook_code=playbook_code,
                parsed_output=parsed_output,
            )

        artifact_registry_id = None
        resolved_project_id = self._resolve_project_id(
            execution_id=execution_id,
            project_id=project_id,
        )
        if (
            resolved_project_id
            and artifact_id
            and landing_result
            and getattr(landing_result, "artifact_dir", None)
        ):
            registry_entry = self._register_project_artifact(
                project_id=resolved_project_id,
                artifact_id=artifact_id,
                artifact_path=landing_result.artifact_dir,
                artifact_type="data",
                created_by=playbook_code or "unknown_playbook",
            )
            artifact_registry_id = getattr(registry_entry, "id", None)

        # Run deterministic acceptance evaluation.
        eval_result_dict = None
        correctness_signals = None
        try:
            from backend.app.services.orchestration.acceptance_evaluator import (
                AcceptanceEvaluator,
            )

            # Resolve acceptance_tests from task governance context
            acceptance_tests = self._resolve_acceptance_tests(execution_id)

            evaluator = AcceptanceEvaluator()
            eval_result = evaluator.evaluate(
                result_data=result_data,
                parsed_output=parsed_output,
                acceptance_tests=acceptance_tests,
                playbook_code=playbook_code,
            )
            eval_result_dict = eval_result.to_dict()
        except Exception as exc:
            logger.warning(
                "GovernanceEngine: AcceptanceEvaluator failed (non-fatal): %s",
                exc,
            )

        # Trigger remediation follow-up when the evaluation fails.
        remediation_decision = None
        if eval_result_dict and not eval_result_dict.get("passed"):
            try:
                remediation_decision = self._trigger_follow_up(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    artifact_id=artifact_id,
                    playbook_code=playbook_code,
                    eval_result=eval_result_dict,
                )
            except Exception as exc:
                logger.warning(
                    "GovernanceEngine: follow-up trigger failed (non-fatal): %s",
                    exc,
                )

        if eval_result_dict:
            correctness_signals = self._sync_correctness_signals(
                execution_id=execution_id,
                artifact_id=artifact_id,
                playbook_code=playbook_code,
                eval_summary=eval_result_dict,
                remediation=remediation_decision,
            )
            if artifact_id:
                self._backfill_eval_summary(
                    artifact_id=artifact_id,
                    eval_summary=eval_result_dict,
                )

        return {
            "success": landing_result is not None,
            "execution_id": execution_id,
            "artifact_id": artifact_id,
            "artifact_registry_id": artifact_registry_id,
            "parsed_output": parsed_output,
            "eval_result": eval_result_dict,
            "correctness_signals": correctness_signals,
            "remediation": remediation_decision,
        }

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
        """Handle cloud terminal events and bridge success back to completion ingress."""
        from backend.app.models.workspace import TaskStatus

        normalized_status = (status or "").strip().lower()
        success_statuses = {"succeeded", "completed"}
        failure_statuses = {"failed", "cancelled", "timeout"}
        if normalized_status not in success_statuses | failure_statuses:
            return {
                "success": False,
                "execution_id": execution_id,
                "error": f"unsupported remote terminal status: {status}",
            }

        task = self.tasks_store.get_task_by_execution_id(execution_id)
        if not task:
            return {
                "success": False,
                "execution_id": execution_id,
                "error": "execution shell not found",
                "error_code": "EXECUTION_SHELL_NOT_FOUND",
            }

        terminal_statuses = {
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELLED_BY_USER.value,
            TaskStatus.EXPIRED.value,
        }
        current_status = getattr(getattr(task, "status", None), "value", None) or str(
            getattr(task, "status", "")
        )
        if current_status in terminal_statuses:
            return {
                "success": True,
                "execution_id": execution_id,
                "idempotent": True,
                "task_status": current_status,
            }

        ctx = dict(getattr(task, "execution_context", None) or {})
        remote_execution = dict(ctx.get("remote_execution") or {})
        remote_execution.update(
            {
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "cloud_dispatch_state": normalized_status,
                "provider_metadata": provider_metadata or {},
            }
        )
        if job_type:
            remote_execution["job_type"] = job_type
        if capability_code:
            remote_execution["capability_code"] = capability_code
        if error_message:
            remote_execution["error"] = error_message
        ctx.update(
            {
                "tenant_id": tenant_id,
                "trace_id": trace_id,
                "remote_execution": remote_execution,
            }
        )
        if job_type and not ctx.get("job_type"):
            ctx["job_type"] = job_type
        if capability_code and not ctx.get("capability_code"):
            ctx["capability_code"] = capability_code
        self.tasks_store.update_task(task.id, execution_context=ctx)

        result_ingress_mode = str(
            remote_execution.get("result_ingress_mode")
            or ctx.get("remote_result_mode")
            or ""
        ).strip().lower()
        is_workflow_step_child = result_ingress_mode == "workflow_step_child"

        if is_workflow_step_child:
            if normalized_status in success_statuses:
                task_status = TaskStatus.SUCCEEDED
            elif normalized_status == "cancelled":
                task_status = TaskStatus.CANCELLED_BY_USER
            else:
                task_status = TaskStatus.FAILED

            child_result = {
                "remote_terminal_status": normalized_status,
                "provider_metadata": provider_metadata or {},
                "result_payload": result_payload,
            }
            self.tasks_store.update_task_status(
                task.id,
                task_status,
                result=child_result,
                error=(
                    None
                    if task_status == TaskStatus.SUCCEEDED
                    else error_message or f"remote execution {normalized_status}"
                ),
                completed_at=datetime.now(timezone.utc),
            )
            return {
                "success": True,
                "execution_id": execution_id,
                "task_id": task.id,
                "task_status": task_status.value,
                "remote_terminal_status": normalized_status,
                "artifact_id": None,
                "result_payload": result_payload,
                "result_ingress_mode": result_ingress_mode,
            }

        if normalized_status in success_statuses:
            completion_result = self.process_completion(
                workspace_id=workspace_id,
                execution_id=execution_id,
                result_data=result_payload or {},
                project_id=getattr(task, "project_id", None)
                or ctx.get("project_id"),
                task_id=task.id,
                playbook_code=playbook_code or ctx.get("playbook_code"),
            ) or {"success": False}
            completion_result["remote_terminal_status"] = normalized_status
            return completion_result

        if normalized_status == "cancelled":
            task_status = TaskStatus.CANCELLED_BY_USER
        else:
            task_status = TaskStatus.FAILED

        self.tasks_store.update_task_status(
            task.id,
            task_status,
            result={
                "remote_terminal_status": normalized_status,
                "provider_metadata": provider_metadata or {},
            },
            error=error_message or f"remote execution {normalized_status}",
        )
        return {
            "success": True,
            "execution_id": execution_id,
            "task_id": task.id,
            "task_status": task_status.value,
            "remote_terminal_status": normalized_status,
            "artifact_id": None,
        }

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
        logger.info(
            "GovernanceEngine.process_playbook_webhook: ingress=%s exec=%s pb=%s",
            "playbook_webhook",
            execution_id,
            playbook_code,
        )
        # Onboarding playbook delegation (backward compat)
        onboarding_codes = {
            "project_breakdown_onboarding",
            "weekly_review_onboarding",
        }
        if playbook_code in onboarding_codes:
            logger.info(
                "GovernanceEngine: delegating onboarding playbook=%s to legacy handler",
                playbook_code,
            )
            try:
                return await self._invoke_legacy_webhook_handler(
                    execution_id=execution_id,
                    playbook_code=playbook_code,
                    user_id=user_id,
                    output_data=output_data,
                    hook="handle_playbook_completion",
                )
            except Exception as exc:
                logger.error(
                    "GovernanceEngine: onboarding delegation failed: %s", exc
                )
                return {"success": False, "error": str(exc)}

        workspace_id = self._resolve_workspace_id(
            execution_id=execution_id,
            output_data=output_data,
        )
        completion_result = self.process_completion(
            workspace_id=workspace_id,
            execution_id=execution_id,
            result_data=output_data,
            playbook_code=playbook_code,
        ) or {"success": False}

        response: Dict[str, Any] = {
            **completion_result,
            "playbook_code": playbook_code,
            "created_resources": {},
        }

        if completion_result.get("success"):
            try:
                post_landing = await self._invoke_legacy_webhook_handler(
                    execution_id=execution_id,
                    playbook_code=playbook_code,
                    user_id=user_id,
                    output_data=output_data,
                    hook="handle_post_landing_completion",
                )
                if isinstance(post_landing, dict):
                    response["created_resources"] = post_landing.get(
                        "created_resources", {}
                    )
                    if post_landing.get("message"):
                        response["message"] = post_landing["message"]
                    response["post_landing_hook"] = post_landing
            except Exception as exc:
                logger.warning(
                    "GovernanceEngine: regular post-landing hook failed (non-fatal): %s",
                    exc,
                )

        return response

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
        from backend.app.services.mindscape_store import MindscapeStore
        from backend.app.services.playbook_webhook import PlaybookWebhookHandler

        handler = PlaybookWebhookHandler(MindscapeStore())
        method = getattr(handler, hook)
        return await method(
            execution_id=execution_id,
            playbook_code=playbook_code,
            user_id=user_id,
            output_data=output_data,
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
        try:
            from backend.app.services.mindscape_store import MindscapeStore
            from backend.app.services.project.artifact_registry_service import (
                ArtifactRegistryService,
            )

            registry = ArtifactRegistryService(MindscapeStore())
            existing = registry.get_artifact_sync(project_id, artifact_id)
            if existing:
                return existing

            return registry.register_artifact_sync(
                project_id=project_id,
                artifact_id=artifact_id,
                path=artifact_path,
                artifact_type=artifact_type,
                created_by=created_by,
            )
        except Exception as exc:
            logger.warning(
                "GovernanceEngine: artifact registry registration failed (non-fatal): %s",
                exc,
            )
            return None

    def _update_artifact_metadata(
        self,
        *,
        artifact_id: str,
        updater,
    ) -> bool:
        """Load artifact metadata, apply update, and persist it."""
        from backend.app.services.stores.postgres.artifacts_store import (
            PostgresArtifactsStore,
        )

        store = PostgresArtifactsStore()
        artifact = store.get_artifact(artifact_id)
        if not artifact:
            logger.debug(
                "GovernanceEngine: artifact %s not found for metadata update",
                artifact_id,
            )
            return False

        existing_metadata = (
            artifact.metadata if isinstance(artifact.metadata, dict) else {}
        )
        updater(existing_metadata)
        store.update_artifact(artifact_id, metadata=existing_metadata)
        return True

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
        1.  GET artifact → read existing metadata
        2.  Deep merge ``parsed_output`` into ``metadata.provenance``
        3.  PUT updated metadata back via ``update_artifact``
        4.  Mark handoff_registry entries as completed

        All errors are logged and swallowed — backfill must never
        break the completion flow.
        """
        # --- 1. Artifact metadata merge ---
        try:
            def _merge_provenance(metadata: Dict[str, Any]) -> None:
                provenance = (
                    metadata.get("provenance")
                    if isinstance(metadata.get("provenance"), dict)
                    else {}
                )
                provenance.update(parsed_output)

                # ADR-003: enrich with meeting-level provenance
                try:
                    task = self.tasks_store.get_task_by_execution_id(execution_id)
                    if task:
                        ctx = getattr(task, "execution_context", None) or {}
                        msid = getattr(task, "meeting_session_id", None) or ctx.get(
                            "meeting_session_id"
                        )
                        if msid:
                            provenance.setdefault("meeting_session_id", msid)
                        pid = getattr(task, "project_id", None) or (
                            getattr(task, "params", None) or {}
                        ).get("project_id")
                        if pid:
                            provenance.setdefault("project_id", pid)
                        provenance.setdefault("source_task_id", task.id)
                except Exception:
                    pass

                metadata["provenance"] = provenance

            updated = self._update_artifact_metadata(
                artifact_id=artifact_id,
                updater=_merge_provenance,
            )
            if updated:
                logger.info(
                    "GovernanceEngine: provenance backfilled artifact=%s hash=%s",
                    artifact_id,
                    parsed_output.get("output_hash", "")[:12]
                    if parsed_output.get("output_hash")
                    else "none",
                )
        except Exception as exc:
            logger.warning(
                "GovernanceEngine: artifact provenance backfill failed (non-fatal): %s",
                exc,
            )

        # --- 2. Handoff registry completion ---
        try:
            from backend.app.services.stores.handoff_registry_store import (
                HandoffRegistryStore,
            )

            # Resolve task_ir_id from task context
            task_ir_id = None
            try:
                task = self.tasks_store.get_task_by_execution_id(execution_id)
                if task:
                    ctx = getattr(task, "execution_context", None) or {}
                    task_ir_id = ctx.get("task_ir_id")
            except Exception:
                pass

            if task_ir_id:
                registry = HandoffRegistryStore()
                registry.mark_completed(
                    task_ir_id=task_ir_id,
                    execution_id=execution_id,
                    artifact_id=artifact_id,
                )
        except Exception as exc:
            logger.warning(
                "GovernanceEngine: handoff registry completion failed (non-fatal): %s",
                exc,
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
