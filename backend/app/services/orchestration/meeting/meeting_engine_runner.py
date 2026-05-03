"""Shared runner for command-ledger MeetingEngine orchestration."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_command import MeetingCommandRecord
from backend.app.models.route_decision import (
    ExecutionProfileKind,
    RouteDecision,
    RouteKind,
    RouteReasonCode,
)
from backend.app.services.orchestration.meeting import MeetingEngine, MeetingResult

logger = logging.getLogger(__name__)


def _as_dict(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if hasattr(value, "model_dump"):
        dumped = value.model_dump(exclude_none=True)
        return dict(dumped) if isinstance(dumped, dict) else {}
    return {}


def _artifact_payload(artifact: Any) -> Dict[str, Any]:
    if hasattr(artifact, "model_dump"):
        return artifact.model_dump(exclude_none=True)
    return dict(artifact) if isinstance(artifact, dict) else {}


def _artifact_file_path(payload: Dict[str, Any]) -> Optional[str]:
    metadata = _as_dict(payload.get("metadata"))
    for key in ("file_path", "actual_file_path", "storage_ref"):
        value = payload.get(key) or metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    uri = payload.get("uri")
    if isinstance(uri, str) and uri.startswith("/"):
        return uri
    return None


class MeetingEngineRunner:
    """Construct, run, and persist MeetingEngine results for command ledger rows."""

    def __init__(self, *, store: Any, session_store: Any) -> None:
        self.store = store
        self.session_store = session_store

    async def run_meeting_orchestration(
        self,
        *,
        session: Any,
        workspace: Any,
        message: str,
        handoff_in: Any,
        command: MeetingCommandRecord,
    ) -> dict:
        try:
            return await self._run(
                session=session,
                workspace=workspace,
                message=message,
                handoff_in=handoff_in,
                command=command,
            )
        except Exception as exc:
            logger.exception("Meeting command orchestration failed for %s", command.command_id)
            return {
                "status": "failed",
                "session_id": getattr(session, "id", command.meeting_id),
                "task_ir_id": None,
                "event_ids": [],
                "minutes_md": "",
                "completion_status": "failed",
                "dispatch_result": None,
                "task_ir_artifacts": [],
                "artifact_ids": [],
                "artifact_file_paths": [],
                "artifact_landing_status": "failed",
                "request_contract_aol_metadata": self._request_contract_aol_metadata(session),
                "request_contract_aol_metadata_persisted": False,
                "error": str(exc),
            }

    async def _run(
        self,
        *,
        session: Any,
        workspace: Any,
        message: str,
        handoff_in: Any,
        command: MeetingCommandRecord,
    ) -> dict:
        runtime_profile = await self._resolve_runtime_profile(workspace)
        if runtime_profile is None:
            return self._missing_dependency_result(
                session=session,
                dependency="runtime_profile",
                message="Unable to resolve workspace runtime profile.",
            )

        from backend.app.models.meeting_execution_context import MeetingExecutionContext
        from backend.app.services.conversation.pipeline_meeting import (
            build_execution_launcher,
            persist_meeting_task_ir,
        )
        from backend.app.services.executor_routing_policy_service import (
            ExecutorRoutingPolicyService,
        )

        route_decision = RouteDecision(
            route_kind=RouteKind.MEETING,
            execution_profile=ExecutionProfileKind.DURABLE,
            reason_codes=[RouteReasonCode.PROJECT_MEETING_ENABLED],
            source_entry_point="meeting_command",
        )
        execution_launcher = build_execution_launcher(self.store)
        executor_runtime = (
            ExecutorRoutingPolicyService.extract_workspace_policy_snapshot(workspace).get(
                "primary_executor_runtime"
            )
        )
        execution_context = MeetingExecutionContext.assemble(
            workspace=workspace,
            runtime_profile=runtime_profile,
            route_decision=route_decision,
        )
        engine = MeetingEngine(
            session=session,
            store=self.store,
            workspace=workspace,
            runtime_profile=runtime_profile,
            profile_id=getattr(workspace, "owner_user_id", None) or "meeting_engine",
            thread_id=getattr(session, "thread_id", None) or command.thread_id or command.meeting_id,
            project_id=getattr(session, "project_id", None)
            or getattr(workspace, "primary_project_id", None),
            execution_launcher=execution_launcher,
            model_name=self._resolve_model_name(runtime_profile, session),
            executor_runtime=executor_runtime,
            uploaded_files=[],
            execution_context=execution_context,
        )
        meeting_result: MeetingResult = await engine.run(message, handoff_in=handoff_in)

        if meeting_result.task_ir:
            await persist_meeting_task_ir(meeting_result.task_ir)

        request_contract_aol = self._request_contract_aol_metadata(session)
        persisted_metadata = False
        if request_contract_aol:
            try:
                self.session_store.update(session)
                persisted_metadata = True
            except Exception as exc:
                logger.warning(
                    "Failed to persist meeting session metadata for %s: %s",
                    getattr(session, "id", None),
                    exc,
                    exc_info=True,
                )

        artifacts = [
            _artifact_payload(item)
            for item in list(getattr(meeting_result.task_ir, "artifacts", []) or [])
        ] if meeting_result.task_ir else []
        artifact_ids = [
            str(item.get("id")).strip()
            for item in artifacts
            if str(item.get("id") or "").strip()
        ]
        artifact_file_paths = [
            path for path in (_artifact_file_path(item) for item in artifacts) if path
        ]
        artifact_landing_status = self._artifact_landing_status(
            artifact_ids=artifact_ids,
            artifact_file_paths=artifact_file_paths,
        )

        return {
            "status": "completed",
            "session_id": meeting_result.session_id,
            "task_ir_id": (
                meeting_result.task_ir.task_id if meeting_result.task_ir else None
            ),
            "event_ids": list(meeting_result.event_ids or []),
            "minutes_md": meeting_result.minutes_md or "",
            "completion_status": meeting_result.completion_status,
            "dispatch_result": meeting_result.dispatch_result,
            "task_ir_artifacts": artifacts,
            "artifact_ids": artifact_ids,
            "artifact_file_paths": artifact_file_paths,
            "artifact_landing_status": artifact_landing_status,
            "request_contract_aol_metadata": request_contract_aol,
            "request_contract_aol_metadata_persisted": persisted_metadata,
        }

    async def _resolve_runtime_profile(self, workspace: Any) -> Optional[Any]:
        from backend.app.services.stores.workspace_runtime_profile_store import (
            WorkspaceRuntimeProfileStore,
        )

        workspace_id = getattr(workspace, "id", None)
        if not workspace_id:
            return None
        store = WorkspaceRuntimeProfileStore()
        runtime_profile = await store.get_runtime_profile(workspace_id)
        if runtime_profile is None:
            runtime_profile = await store.create_default_profile(workspace_id)
        if hasattr(runtime_profile, "ensure_phase2_fields"):
            runtime_profile.ensure_phase2_fields()
        return runtime_profile

    @staticmethod
    def _resolve_model_name(runtime_profile: Any, session: Any) -> Optional[str]:
        session_metadata = getattr(session, "metadata", None) or {}
        for value in (
            session_metadata.get("model_name"),
            getattr(runtime_profile, "model_name", None),
            getattr(runtime_profile, "default_model", None),
        ):
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    @staticmethod
    def _request_contract_aol_metadata(session: Any) -> Dict[str, Any]:
        metadata = getattr(session, "metadata", None) or {}
        request_contract = metadata.get("request_contract")
        if not isinstance(request_contract, dict):
            return {}
        return _as_dict(request_contract.get("addressable_object_layer"))

    @staticmethod
    def _artifact_landing_status(
        *, artifact_ids: List[str], artifact_file_paths: List[str]
    ) -> str:
        if not artifact_ids:
            return "not_requested"
        if artifact_file_paths:
            return "landed"
        return "pending"

    def _missing_dependency_result(
        self,
        *,
        session: Any,
        dependency: str,
        message: str,
    ) -> dict:
        return {
            "status": "failed",
            "session_id": getattr(session, "id", None),
            "task_ir_id": None,
            "event_ids": [],
            "minutes_md": "",
            "completion_status": "failed",
            "dispatch_result": None,
            "task_ir_artifacts": [],
            "artifact_ids": [],
            "artifact_file_paths": [],
            "artifact_landing_status": "failed",
            "request_contract_aol_metadata": self._request_contract_aol_metadata(session),
            "request_contract_aol_metadata_persisted": False,
            "missing_dependency": dependency,
            "error": message,
        }
