"""Shared runner for command-ledger MeetingEngine orchestration."""

from __future__ import annotations

import logging
import asyncio
import uuid
from typing import Any, Dict, List, Optional

from backend.app.models.meeting_command import MeetingCommandRecord
from backend.app.models.route_decision import (
    ExecutionProfileKind,
    RouteDecision,
    RouteKind,
    RouteReasonCode,
)
from backend.app.models.workspace import Artifact, ArtifactType as WorkspaceArtifactType
from backend.app.models.workspace import PrimaryActionType
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


def _artifact_model_file_path(artifact: Any) -> Optional[str]:
    metadata = _as_dict(getattr(artifact, "metadata", None))
    for key in ("actual_file_path", "file_path", "storage_ref"):
        value = _clean_string(metadata.get(key))
        if value:
            return value
    storage_ref = _clean_string(getattr(artifact, "storage_ref", None))
    if storage_ref:
        return storage_ref
    return None


def _artifact_model_content(artifact: Any) -> Dict[str, Any]:
    return _as_dict(getattr(artifact, "content", None))


def _clean_string(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _append_unique(values: List[str], value: Optional[str]) -> None:
    if value and value not in values:
        values.append(value)


def _dispatch_execution_ids(value: Any, *, depth: int = 0) -> List[str]:
    if depth > 8:
        return []
    found: List[str] = []
    if isinstance(value, dict):
        execution_id = _clean_string(value.get("execution_id"))
        if execution_id:
            found.append(execution_id)
        for nested in value.values():
            for nested_id in _dispatch_execution_ids(nested, depth=depth + 1):
                _append_unique(found, nested_id)
    elif isinstance(value, list):
        for item in value:
            for nested_id in _dispatch_execution_ids(item, depth=depth + 1):
                _append_unique(found, nested_id)
    return found


def _execution_artifact_failure_reason(artifact: Any) -> Optional[str]:
    content = _artifact_model_content(artifact)
    if not content:
        return None

    status = (_clean_string(content.get("status")) or "").lower()
    if status in {"error", "failed", "failure"}:
        return _clean_string(content.get("error")) or f"execution_status:{status}"

    steps = _as_dict(content.get("steps"))
    for step_id, raw_step in steps.items():
        step = _as_dict(raw_step)
        step_status = (_clean_string(step.get("status")) or "").lower()
        if step_status in {"error", "failed", "failure"}:
            reason = _clean_string(step.get("error")) or f"step_status:{step_status}"
            return f"step_failed:{step_id}:{reason}"

    result = _as_dict(content.get("result"))
    if result.get("success") is False:
        return _clean_string(result.get("error")) or "result_success_false"

    output = _as_dict(content.get("output"))
    if output.get("success") is False:
        return _clean_string(output.get("error")) or "output_success_false"

    return None


def _execution_artifacts(lookup_store: Any, execution_id: str) -> List[Any]:
    if hasattr(lookup_store, "list_by_execution_id"):
        artifacts = lookup_store.list_by_execution_id(execution_id)
        if artifacts is None:
            return []
        if isinstance(artifacts, list):
            return artifacts
        return list(artifacts)

    if hasattr(lookup_store, "get_by_execution_id"):
        artifact = lookup_store.get_by_execution_id(execution_id)
        return [artifact] if artifact is not None else []

    return []


def _workspace_artifact_type(payload: Dict[str, Any]) -> WorkspaceArtifactType:
    metadata = _as_dict(payload.get("metadata"))
    raw_type = _clean_string(
        metadata.get("workspace_artifact_type") or metadata.get("artifact_type")
    )
    if raw_type:
        try:
            return WorkspaceArtifactType(raw_type.lower())
        except ValueError:
            pass

    mime_type = _clean_string(payload.get("type") or metadata.get("mime_type")) or ""
    uri = _clean_string(payload.get("uri")) or ""
    candidate = f"{mime_type} {uri}".lower()
    if "image/" in candidate or candidate.endswith(
        (".png", ".jpg", ".jpeg", ".webp")
    ):
        return WorkspaceArtifactType.IMAGE
    if "video/" in candidate or candidate.endswith((".mp4", ".mov", ".webm")):
        return WorkspaceArtifactType.VIDEO
    if "audio/" in candidate or candidate.endswith((".mp3", ".wav", ".m4a")):
        return WorkspaceArtifactType.AUDIO
    if "json" in candidate:
        return WorkspaceArtifactType.DATA
    if (
        "markdown" in candidate
        or "text/" in candidate
        or candidate.endswith((".md", ".txt"))
    ):
        return WorkspaceArtifactType.DRAFT
    return WorkspaceArtifactType.FILE


def _workspace_primary_action_type(storage_ref: Optional[str]) -> PrimaryActionType:
    if storage_ref and storage_ref.startswith(("http://", "https://")):
        return PrimaryActionType.OPEN_EXTERNAL
    if storage_ref:
        return PrimaryActionType.DOWNLOAD
    return PrimaryActionType.PREVIEW


def _workspace_artifact_from_task_ir_payload(
    payload: Dict[str, Any],
    *,
    workspace_id: str,
    thread_id: str,
    task_id: Optional[str],
    command: MeetingCommandRecord,
    request_contract_aol: Dict[str, Any],
) -> Artifact:
    metadata = _as_dict(payload.get("metadata"))
    artifact_id = (
        _clean_string(payload.get("id"))
        or f"meeting_artifact_{uuid.uuid4().hex}"
    )
    storage_ref = _artifact_file_path(payload) or _clean_string(payload.get("uri"))
    title = (
        _clean_string(payload.get("title"))
        or _clean_string(metadata.get("title"))
        or artifact_id
    )
    summary = (
        _clean_string(payload.get("summary"))
        or _clean_string(metadata.get("summary"))
        or "Artifact produced by MeetingEngine orchestration."
    )
    source = (
        _clean_string(payload.get("source") or metadata.get("source"))
        or "meeting_engine"
    )
    playbook_code = (
        _clean_string(metadata.get("playbook_code"))
        or (source.split(":", 1)[1] if source.startswith("playbook:") else None)
        or "meeting_engine"
    )
    content = _as_dict(payload.get("content"))
    if not content:
        content = {"task_ir_artifact": payload}
    artifact_metadata = {
        **metadata,
        "meeting_id": command.meeting_id,
        "command_id": command.command_id,
        "thread_id": thread_id,
        "artifact_landing_source": "meeting_engine_task_ir",
        "source_task_ir_artifact": payload,
    }
    if request_contract_aol:
        artifact_metadata["request_contract_aol_metadata"] = request_contract_aol
    if storage_ref:
        artifact_metadata.setdefault("file_path", storage_ref)

    return Artifact(
        id=artifact_id,
        workspace_id=workspace_id,
        intent_id=_clean_string(metadata.get("intent_id")),
        task_id=task_id,
        execution_id=_clean_string(
            payload.get("execution_id") or metadata.get("execution_id") or task_id
        ),
        thread_id=thread_id,
        playbook_code=playbook_code,
        artifact_type=_workspace_artifact_type(payload),
        title=title,
        summary=summary,
        content=content,
        storage_ref=storage_ref,
        sync_state=None,
        primary_action_type=_workspace_primary_action_type(storage_ref),
        metadata=artifact_metadata,
    )


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
        artifact_landing = self._land_task_ir_artifacts(
            artifacts=artifacts,
            workspace=workspace,
            session=session,
            task_id=meeting_result.task_ir.task_id if meeting_result.task_ir else None,
            command=command,
            request_contract_aol=request_contract_aol,
        )
        dispatch_artifacts = await self._dispatch_artifact_refs(
            meeting_result.dispatch_result,
            artifacts_store=getattr(self.store, "artifacts", None),
        )
        for artifact_id in dispatch_artifacts["artifact_db_ids"]:
            _append_unique(artifact_ids, artifact_id)
            _append_unique(artifact_landing["artifact_db_ids"], artifact_id)
        for artifact_path in dispatch_artifacts["artifact_file_paths"]:
            _append_unique(artifact_file_paths, artifact_path)
        artifact_execution_errors = dispatch_artifacts["artifact_execution_errors"]
        artifact_landing_status = self._artifact_landing_status(
            artifact_ids=artifact_ids,
            artifact_file_paths=artifact_file_paths,
            artifact_db_ids=artifact_landing["artifact_db_ids"],
            artifact_execution_errors=artifact_execution_errors,
            artifact_missing_file_paths=dispatch_artifacts[
                "artifact_file_path_missing_count"
            ],
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
            "artifact_db_ids": artifact_landing["artifact_db_ids"],
            "artifact_db_errors": artifact_landing["artifact_db_errors"],
            "artifact_execution_errors": artifact_execution_errors,
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
        *,
        artifact_ids: List[str],
        artifact_file_paths: List[str],
        artifact_db_ids: List[str],
        artifact_execution_errors: Optional[List[Dict[str, str]]] = None,
        artifact_missing_file_paths: int = 0,
    ) -> str:
        if artifact_execution_errors:
            return "failed"
        if not artifact_ids:
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
    ) -> Dict[str, Any]:
        execution_ids = _dispatch_execution_ids(dispatch_result)
        if not execution_ids:
            return {
                "artifact_db_ids": [],
                "artifact_file_paths": [],
                "artifact_execution_errors": [],
                "artifact_file_path_missing_count": 0,
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
            }

        result = {
            "artifact_db_ids": [],
            "artifact_file_paths": [],
            "artifact_execution_errors": [],
            "artifact_file_path_missing_count": 0,
        }
        for attempt_index in range(16):
            artifact_db_ids: List[str] = []
            artifact_file_paths: List[str] = []
            artifact_execution_errors: List[Dict[str, str]] = []
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
            }
            if artifact_execution_errors:
                return result
            if artifact_db_ids and missing_file_paths == 0:
                return result
            if attempt_index < 15:
                await asyncio.sleep(0.5)
        return result

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
            "artifact_db_ids": [],
            "artifact_db_errors": [],
            "artifact_landing_status": "failed",
            "request_contract_aol_metadata": self._request_contract_aol_metadata(session),
            "request_contract_aol_metadata_persisted": False,
            "missing_dependency": dependency,
            "error": message,
        }
