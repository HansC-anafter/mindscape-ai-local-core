"""Artifact landing and dispatch lookup mixin for MeetingEngineRunner."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_command import MeetingCommandRecord
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.artifact_helpers import (
    _append_unique,
    _artifact_model_content,
    _artifact_model_file_path,
    _as_dict,
    _clean_string,
    _dispatch_execution_ids,
    _execution_artifact_failure_reason,
    _execution_artifacts,
    _workspace_artifact_from_task_ir_payload,
)
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.quality_input import (
    _producer_eval_summaries_from_value,
)
from backend.app.services.orchestration.meeting.meeting_engine_runner_core.quality_policy import (
    _producer_eval_required_by_quality_requirements,
    _quality_requirements_from_aol_metadata,
)

logger = logging.getLogger(__name__)


class MeetingEngineRunnerArtifactLandingMixin:
    @staticmethod
    def _artifact_landing_status(
        *,
        artifact_ids: List[str],
        artifact_file_paths: List[str],
        artifact_db_ids: List[str],
        artifact_execution_errors: Optional[List[Dict[str, str]]] = None,
        artifact_missing_file_paths: int = 0,
        pending_execution_ids: Optional[List[str]] = None,
    ) -> str:
        if artifact_execution_errors:
            return "failed"
        if not artifact_ids:
            if pending_execution_ids:
                return "pending"
            return "not_requested"
        if artifact_missing_file_paths > 0:
            return "pending"
        if len(artifact_db_ids) >= len(artifact_ids) and artifact_file_paths:
            return "landed"
        return "pending"

    def _land_task_ir_artifacts(
        self,
        *,
        artifacts: List[Dict[str, Any]],
        workspace: Any,
        session: Any,
        task_id: Optional[str],
        command: MeetingCommandRecord,
        request_contract_aol: Dict[str, Any],
    ) -> Dict[str, Any]:
        if not artifacts:
            return {"artifact_db_ids": [], "artifact_db_errors": []}

        artifacts_store = getattr(self.store, "artifacts", None)
        if artifacts_store is None or not hasattr(artifacts_store, "create_artifact"):
            return {
                "artifact_db_ids": [],
                "artifact_db_errors": [
                    {
                        "code": "artifact_store_unavailable",
                        "message": "MindscapeStore.artifacts is unavailable; TaskIR artifacts remain pending DB landing.",
                    }
                ],
            }

        workspace_id = getattr(workspace, "id", None) or command.workspace_id
        thread_id = (
            getattr(session, "thread_id", None)
            or command.thread_id
            or command.meeting_id
        )
        artifact_db_ids: List[str] = []
        artifact_db_errors: List[Dict[str, str]] = []
        for payload in artifacts:
            try:
                artifact = _workspace_artifact_from_task_ir_payload(
                    payload,
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    task_id=task_id,
                    command=command,
                    request_contract_aol=request_contract_aol,
                )
                existing = None
                if hasattr(artifacts_store, "get_artifact"):
                    existing = artifacts_store.get_artifact(artifact.id)
                if existing is None:
                    artifacts_store.create_artifact(artifact)
                artifact_db_ids.append(artifact.id)
            except Exception as exc:
                artifact_id = _clean_string(payload.get("id")) or "unknown"
                logger.warning(
                    "Failed to land MeetingEngine artifact %s for command %s: %s",
                    artifact_id,
                    command.command_id,
                    exc,
                    exc_info=True,
                )
                artifact_db_errors.append(
                    {
                        "artifact_id": artifact_id,
                        "error": str(exc),
                    }
                )
        return {
            "artifact_db_ids": artifact_db_ids,
            "artifact_db_errors": artifact_db_errors,
        }

    async def _dispatch_artifact_refs(
        self,
        dispatch_result: Any,
        *,
        artifacts_store: Any,
        wait_seconds: Optional[float] = None,
    ) -> Dict[str, Any]:
        execution_ids = _dispatch_execution_ids(dispatch_result)
        if not execution_ids:
            return {
                "artifact_db_ids": [],
                "artifact_file_paths": [],
                "artifact_execution_errors": [],
                "artifact_file_path_missing_count": 0,
                "producer_eval_summaries": [],
            }

        lookup_store = artifacts_store
        if lookup_store is None or not (
            hasattr(lookup_store, "list_by_execution_id")
            or hasattr(lookup_store, "get_by_execution_id")
        ):
            try:
                from backend.app.services.stores.postgres.artifacts_store import (
                    PostgresArtifactsStore,
                )

                lookup_store = PostgresArtifactsStore()
            except Exception:
                lookup_store = None
        if lookup_store is None or not (
            hasattr(lookup_store, "list_by_execution_id")
            or hasattr(lookup_store, "get_by_execution_id")
        ):
            return {
                "artifact_db_ids": [],
                "artifact_file_paths": [],
                "artifact_execution_errors": [],
                "artifact_file_path_missing_count": 0,
                "producer_eval_summaries": [],
            }

        result = {
            "artifact_db_ids": [],
            "artifact_file_paths": [],
            "artifact_execution_errors": [],
            "artifact_file_path_missing_count": 0,
            "producer_eval_summaries": [],
        }
        poll_interval_seconds = 0.5
        if wait_seconds is None:
            wait_seconds = 8.0
        try:
            wait_seconds = float(wait_seconds)
        except (TypeError, ValueError):
            wait_seconds = 8.0
        wait_seconds = min(max(wait_seconds, poll_interval_seconds), 3600.0)
        max_attempts = max(1, int(wait_seconds / poll_interval_seconds))

        for attempt_index in range(max_attempts):
            artifact_db_ids: List[str] = []
            artifact_file_paths: List[str] = []
            artifact_execution_errors: List[Dict[str, str]] = []
            producer_eval_summaries: List[Dict[str, Any]] = []
            missing_file_paths = 0

            for execution_id in execution_ids:
                try:
                    artifacts = _execution_artifacts(lookup_store, execution_id)
                except Exception:
                    logger.debug(
                        "MeetingEngine dispatch artifact lookup skipped for execution %s",
                        execution_id,
                        exc_info=True,
                    )
                    continue
                for artifact in artifacts:
                    failure_reason = _execution_artifact_failure_reason(artifact)
                    if failure_reason:
                        artifact_execution_errors.append(
                            {
                                "execution_id": execution_id,
                                "artifact_id": _clean_string(
                                    getattr(artifact, "id", None)
                                )
                                or "unknown",
                                "error": failure_reason,
                            }
                        )
                        continue

                    artifact_id = _clean_string(getattr(artifact, "id", None))
                    _append_unique(artifact_db_ids, artifact_id)
                    metadata = _as_dict(getattr(artifact, "metadata", None))
                    raw_kind = _clean_string(
                        metadata.get("artifact_kind")
                        or metadata.get("raw_artifact_kind")
                    )
                    for container, source in (
                        (metadata, "dispatch_artifact_metadata"),
                        (_artifact_model_content(artifact), "dispatch_artifact_content"),
                    ):
                        producer_eval_summaries.extend(
                            _producer_eval_summaries_from_value(
                                container,
                                source=source,
                                artifact_id=artifact_id,
                                artifact_kind=raw_kind,
                                execution_id=execution_id,
                            )
                        )
                    artifact_path = _artifact_model_file_path(artifact)
                    if artifact_path:
                        _append_unique(artifact_file_paths, artifact_path)
                    elif artifact_id:
                        missing_file_paths += 1

            result = {
                "artifact_db_ids": artifact_db_ids,
                "artifact_file_paths": artifact_file_paths,
                "artifact_execution_errors": artifact_execution_errors,
                "artifact_file_path_missing_count": missing_file_paths,
                "producer_eval_summaries": producer_eval_summaries,
            }
            if artifact_execution_errors:
                return result
            if artifact_db_ids and missing_file_paths == 0:
                return result
            if attempt_index < max_attempts - 1:
                await asyncio.sleep(poll_interval_seconds)
        return result

    @staticmethod
    def _dispatch_artifact_wait_seconds(
        *,
        command: MeetingCommandRecord,
        request_contract_aol: Dict[str, Any],
    ) -> float:
        quality_requirements = _quality_requirements_from_aol_metadata(
            request_contract_aol
        )
        if not _producer_eval_required_by_quality_requirements(quality_requirements):
            return 8.0
        metadata = _as_dict(getattr(command, "metadata", None))
        raw_timeout = metadata.get("meeting_orchestration_timeout_seconds")
        try:
            timeout = float(raw_timeout)
        except (TypeError, ValueError):
            timeout = 300.0
        return min(max(timeout, 8.0), 3600.0)
