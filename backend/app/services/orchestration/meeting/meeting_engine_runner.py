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
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.artifact_helpers import (
    _append_unique,
    _artifact_file_path,
    _artifact_model_content,
    _artifact_model_file_path,
    _artifact_payload,
    _as_dict,
    _clean_string,
    _dispatch_execution_ids,
    _execution_artifact_failure_reason,
    _execution_artifacts,
    _workspace_artifact_from_task_ir_payload,
    _workspace_artifact_type,
    _workspace_primary_action_type,
)
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.artifact_landing_mixin import (
    MeetingEngineRunnerArtifactLandingMixin,
)
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.quality_input import (
    _normalize_producer_eval_summary,
    _producer_eval_summaries_from_value,
    _producer_review_result,
    _raw_producer_eval_summaries,
    _strict_quality_gate_rollup,
)
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.quality_policy import (
    _bounded_json,
    _extract_json_object,
    _normalize_meeting_quality_review,
    _producer_eval_required_by_quality_requirements,
    _producer_quality_gate_fallback,
    _producer_rewrite_dispatch_request,
    _quality_requirements_from_aol_metadata,
    _rewrite_until_quality_passed,
    _truthy,
)
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.quality_review_mixin import (
    MeetingEngineRunnerQualityReviewMixin,
)
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.runtime_metadata_mixin import (
    MeetingEngineRunnerRuntimeMetadataMixin,
)

logger = logging.getLogger(__name__)


class MeetingEngineRunner(
    MeetingEngineRunnerQualityReviewMixin,
    MeetingEngineRunnerRuntimeMetadataMixin,
    MeetingEngineRunnerArtifactLandingMixin,
):
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
                "artifact_db_ids": [],
                "artifact_db_errors": [],
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
        producer_eval_summaries: List[Dict[str, Any]] = []
        for artifact_payload in artifacts:
            producer_eval_summaries.extend(
                _producer_eval_summaries_from_value(
                    artifact_payload,
                    source="task_ir_artifact",
                    artifact_id=_clean_string(artifact_payload.get("id")),
                    artifact_kind=_clean_string(
                        _as_dict(artifact_payload.get("metadata")).get("artifact_kind")
                    ),
                )
            )
        producer_eval_summaries.extend(
            _producer_eval_summaries_from_value(
                meeting_result.dispatch_result,
                source="dispatch_result",
            )
        )
        artifact_landing = self._land_task_ir_artifacts(
            artifacts=artifacts,
            workspace=workspace,
            session=session,
            task_id=meeting_result.task_ir.task_id if meeting_result.task_ir else None,
            command=command,
            request_contract_aol=request_contract_aol,
        )
        dispatch_execution_ids = _dispatch_execution_ids(meeting_result.dispatch_result)
        artifact_wait_seconds = self._dispatch_artifact_wait_seconds(
            command=command,
            request_contract_aol=request_contract_aol,
        )
        dispatch_artifacts = await self._dispatch_artifact_refs(
            meeting_result.dispatch_result,
            artifacts_store=getattr(self.store, "artifacts", None),
            wait_seconds=artifact_wait_seconds,
        )
        for artifact_id in dispatch_artifacts["artifact_db_ids"]:
            _append_unique(artifact_ids, artifact_id)
            _append_unique(artifact_landing["artifact_db_ids"], artifact_id)
        for artifact_path in dispatch_artifacts["artifact_file_paths"]:
            _append_unique(artifact_file_paths, artifact_path)
        producer_eval_summaries.extend(dispatch_artifacts["producer_eval_summaries"])
        artifact_execution_errors = dispatch_artifacts["artifact_execution_errors"]
        artifact_landing_status = self._artifact_landing_status(
            artifact_ids=artifact_ids,
            artifact_file_paths=artifact_file_paths,
            artifact_db_ids=artifact_landing["artifact_db_ids"],
            artifact_execution_errors=artifact_execution_errors,
            artifact_missing_file_paths=dispatch_artifacts[
                "artifact_file_path_missing_count"
            ],
            pending_execution_ids=dispatch_execution_ids,
        )
        producer_review = _producer_review_result(producer_eval_summaries)
        producer_quality_gate = await self._producer_quality_gate_review(
            engine=engine,
            producer_review=producer_review,
            producer_eval_summaries=producer_eval_summaries,
            request_contract_aol=request_contract_aol,
            task_ir_artifacts=artifacts,
            user_message=message,
        )
        completion_status = producer_quality_gate["completion_status"]
        if (
            producer_review["review_state"] is None
            and meeting_result.completion_status
            and producer_quality_gate["gate_state"] in {"passed", "accept_with_risk"}
        ):
            completion_status = meeting_result.completion_status

        return {
            "status": "completed",
            "session_id": meeting_result.session_id,
            "task_ir_id": (
                meeting_result.task_ir.task_id if meeting_result.task_ir else None
            ),
            "event_ids": list(meeting_result.event_ids or []),
            "minutes_md": meeting_result.minutes_md or "",
            "dispatch_result": meeting_result.dispatch_result,
            "task_ir_artifacts": artifacts,
            "artifact_ids": artifact_ids,
            "artifact_file_paths": artifact_file_paths,
            "artifact_db_ids": artifact_landing["artifact_db_ids"],
            "artifact_db_errors": artifact_landing["artifact_db_errors"],
            "artifact_execution_errors": artifact_execution_errors,
            "artifact_landing_status": artifact_landing_status,
            "producer_eval_summaries": producer_eval_summaries,
            "review_state": producer_review["review_state"],
            "review_reason": producer_review["review_reason"],
            "recommended_actions": producer_review["recommended_actions"],
            "producer_quality_gate": producer_quality_gate,
            "completion_status": completion_status,
            "request_contract_aol_metadata": request_contract_aol,
            "request_contract_aol_metadata_persisted": persisted_metadata,
        }
