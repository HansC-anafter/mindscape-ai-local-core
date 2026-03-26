import logging
import os
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from fastapi import HTTPException


logger = logging.getLogger(__name__)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RemoteExecutionLaunchService:
    """Own local-core remote launch shell creation and cloud dispatch state sync."""

    def __init__(self, *, connector: Any):
        self._connector = connector

    async def dispatch(
        self,
        *,
        playbook_code: str,
        inputs: Optional[Dict[str, Any]],
        workspace_id: Optional[str],
        profile_id: str,
        project_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        execution_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        remote_job_type: str = "playbook",
        remote_request_payload: Optional[Dict[str, Any]] = None,
        capability_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        try:
            connector = self._connector
            if not connector or not connector.is_connected:
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Execution control connector not available. "
                        "Set CLOUD_CONNECTOR_ENABLED=true and configure "
                        "Runtime Environments config_url or "
                        "EXECUTION_CONTROL_API_URL / SITE_HUB_API_URL / CLOUD_API_URL."
                    ),
                )

            if not workspace_id:
                raise HTTPException(
                    status_code=400,
                    detail="workspace_id is required for remote execution",
                )

            tenant_id = tenant_id or os.getenv("CLOUD_TENANT_ID", "default")
            normalized_inputs = dict(inputs or {})
            execution_id = str(
                execution_id or normalized_inputs.get("execution_id") or uuid.uuid4()
            )
            trace_id = str(trace_id or normalized_inputs.get("trace_id") or execution_id)
            normalized_inputs.setdefault("execution_id", execution_id)
            normalized_inputs.setdefault("trace_id", trace_id)
            normalized_inputs.setdefault("tenant_id", tenant_id)
            normalized_inputs.setdefault("profile_id", profile_id)
            if workspace_id:
                normalized_inputs.setdefault("workspace_id", workspace_id)
            if project_id:
                normalized_inputs.setdefault("project_id", project_id)

            cloud_request_payload = self._build_remote_request_payload(
                playbook_code=playbook_code,
                profile_id=profile_id,
                normalized_inputs=normalized_inputs,
                remote_job_type=remote_job_type,
                remote_request_payload=remote_request_payload,
            )

            tasks_store, task = self._ensure_remote_execution_shell(
                playbook_code=playbook_code,
                workspace_id=workspace_id,
                project_id=project_id,
                profile_id=profile_id,
                tenant_id=tenant_id,
                execution_id=execution_id,
                trace_id=trace_id,
                inputs=normalized_inputs,
            )

            result = await connector.start_remote_execution(
                tenant_id=tenant_id,
                playbook_code=playbook_code,
                request_payload=cloud_request_payload,
                workspace_id=workspace_id,
                capability_code=capability_code,
                execution_id=execution_id,
                trace_id=trace_id,
                job_type=remote_job_type,
                callback_payload={"mode": "local_core_terminal_event"},
            )

            remote_ctx = dict(task.execution_context or {})
            remote_exec = dict(remote_ctx.get("remote_execution") or {})
            remote_exec["cloud_dispatch_state"] = result.get("state", "pending")
            remote_exec["cloud_execution_id"] = result.get("id") or execution_id
            remote_ctx["remote_execution"] = remote_exec
            tasks_store.update_task(task.id, execution_context=remote_ctx)

            cloud_execution_id = result.get("id") or execution_id
            if cloud_execution_id != execution_id:
                logger.warning(
                    "Remote execution ID drift detected local=%s cloud=%s playbook=%s",
                    execution_id,
                    cloud_execution_id,
                    playbook_code,
                )

            return {
                "execution_mode": "remote",
                "playbook_code": playbook_code,
                "execution_id": execution_id,
                "trace_id": trace_id,
                "tenant_id": tenant_id,
                "status": result.get("state", "pending"),
                "cloud_execution_id": cloud_execution_id,
                "job_type": remote_job_type,
                "result": {
                    "status": result.get("state", "pending"),
                    "execution_id": execution_id,
                    "note": "Execution dispatched to cloud control plane",
                },
            }
        except HTTPException:
            raise
        except Exception as e:
            try:
                if "tasks_store" in locals() and "task" in locals():
                    remote_ctx = dict(task.execution_context or {})
                    remote_exec = dict(remote_ctx.get("remote_execution") or {})
                    remote_exec["cloud_dispatch_state"] = "dispatch_failed"
                    remote_exec["error"] = str(e)
                    remote_ctx["remote_execution"] = remote_exec
                    tasks_store.update_task(task.id, execution_context=remote_ctx)
                    from backend.app.models.workspace import TaskStatus

                    tasks_store.update_task_status(
                        task.id,
                        TaskStatus.FAILED,
                        error=str(e),
                        completed_at=_utc_now(),
                    )
            except Exception:
                logger.warning(
                    "Failed to mark remote execution shell as failed", exc_info=True
                )
            logger.error("Remote execution dispatch failed: %s", e, exc_info=True)
            raise HTTPException(
                status_code=502,
                detail=f"Cloud dispatch failed: {e}",
            )

    def _ensure_remote_execution_shell(
        self,
        *,
        playbook_code: str,
        workspace_id: str,
        project_id: Optional[str],
        profile_id: str,
        tenant_id: str,
        execution_id: str,
        trace_id: str,
        inputs: Dict[str, Any],
    ):
        """Create a local task shell before remote dispatch."""
        from backend.app.models.workspace import Task, TaskStatus
        from backend.app.services.stores.tasks_store import TasksStore

        tasks_store = TasksStore()
        existing = tasks_store.get_task_by_execution_id(execution_id)
        if existing:
            return tasks_store, existing

        remote_execution = {
            "tenant_id": tenant_id,
            "trace_id": trace_id,
            "cloud_dispatch_state": "queued",
            "cloud_execution_id": execution_id,
        }
        execution_context = {
            "playbook_code": playbook_code,
            "playbook_name": playbook_code,
            "execution_id": execution_id,
            "trace_id": trace_id,
            "tenant_id": tenant_id,
            "status": "queued",
            "execution_mode": "remote",
            "execution_backend_hint": "remote",
            "inputs": inputs,
            "workspace_id": workspace_id,
            "project_id": project_id,
            "profile_id": profile_id,
            "remote_execution": remote_execution,
            "runner_skip_reason": "remote_execution_shell",
        }
        task = Task(
            id=execution_id,
            workspace_id=workspace_id,
            message_id=str(uuid.uuid4()),
            execution_id=execution_id,
            project_id=project_id,
            pack_id=playbook_code,
            task_type="playbook_execution",
            status=TaskStatus.PENDING,
            execution_context=execution_context,
            created_at=_utc_now(),
            started_at=None,
        )
        tasks_store.create_task(task)
        return tasks_store, task

    def _build_remote_request_payload(
        self,
        *,
        playbook_code: str,
        profile_id: str,
        normalized_inputs: Dict[str, Any],
        remote_job_type: str,
        remote_request_payload: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Build a generic remote payload without embedding pack-specific logic."""
        if not isinstance(remote_request_payload, dict):
            return {
                "inputs": normalized_inputs,
                "profile_id": profile_id,
            }

        payload = dict(remote_request_payload)
        nested_inputs = payload.get("inputs")
        if not isinstance(nested_inputs, dict):
            nested_inputs = {}
        merged_inputs = dict(nested_inputs)
        for key, value in normalized_inputs.items():
            merged_inputs.setdefault(key, value)
        payload["inputs"] = merged_inputs

        if remote_job_type == "playbook":
            payload.setdefault("playbook_code", playbook_code)
            payload.setdefault("profile_id", profile_id)

        return payload
