"""Shared runner for command-ledger MeetingEngine orchestration."""

from __future__ import annotations

import logging
import asyncio
import json
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


def _raw_producer_eval_summaries(value: Any, *, depth: int = 0) -> List[Dict[str, Any]]:
    if depth > 8:
        return []
    found: List[Dict[str, Any]] = []
    if isinstance(value, dict):
        direct = value.get("producer_eval_summary")
        if isinstance(direct, dict):
            found.append(dict(direct))
        elif isinstance(direct, list):
            found.extend(dict(item) for item in direct if isinstance(item, dict))

        if (
            value.get("schema_version") == "producer_eval_summary.v1"
            or (
                "review_state" in value
                and "passed" in value
                and (
                    "producer" in value
                    or "pack_code" in value
                    or "artifact_kind" in value
                )
            )
        ):
            found.append(dict(value))

        for nested in value.values():
            found.extend(_raw_producer_eval_summaries(nested, depth=depth + 1))
    elif isinstance(value, list):
        for item in value:
            found.extend(_raw_producer_eval_summaries(item, depth=depth + 1))
    return found


def _normalize_producer_eval_summary(
    raw: Dict[str, Any],
    *,
    source: str,
    artifact_id: Optional[str] = None,
    artifact_kind: Optional[str] = None,
    execution_id: Optional[str] = None,
) -> Dict[str, Any]:
    summary = dict(raw or {})
    summary.setdefault("schema_version", "producer_eval_summary.v1")
    summary.setdefault("source", source)
    if artifact_id:
        summary.setdefault("artifact_id", artifact_id)
    if artifact_kind:
        summary.setdefault("artifact_kind", artifact_kind)
    if execution_id:
        summary.setdefault("execution_id", execution_id)

    review_state = _clean_string(summary.get("review_state"))
    passed = summary.get("passed")
    if isinstance(passed, bool):
        passed_bool: Optional[bool] = passed
    elif passed is None:
        passed_bool = None
    else:
        passed_bool = bool(passed)
    if not review_state:
        review_state = "passed" if passed_bool is True else "needs_revision"
    summary["review_state"] = review_state
    if passed_bool is not None:
        summary["passed"] = passed_bool
    summary["needs_revision"] = bool(
        summary.get("needs_revision")
        or review_state in {"needs_revision", "needs_reference_analysis", "failed"}
        or passed_bool is False
    )
    summary["rewrite_recommended"] = bool(summary.get("rewrite_recommended"))
    summary["needs_reference_analysis"] = bool(
        summary.get("needs_reference_analysis")
        or review_state == "needs_reference_analysis"
    )
    summary.setdefault("blocking_findings", [])
    summary.setdefault("warnings", [])
    summary.setdefault("recommended_actions", [])
    return summary


def _producer_eval_summaries_from_value(
    value: Any,
    *,
    source: str,
    artifact_id: Optional[str] = None,
    artifact_kind: Optional[str] = None,
    execution_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    summaries: List[Dict[str, Any]] = []
    seen = set()
    for raw in _raw_producer_eval_summaries(value):
        normalized = _normalize_producer_eval_summary(
            raw,
            source=source,
            artifact_id=artifact_id,
            artifact_kind=artifact_kind,
            execution_id=execution_id,
        )
        key = (
            normalized.get("artifact_id"),
            normalized.get("artifact_kind"),
            normalized.get("review_state"),
            str(normalized.get("score")),
        )
        if key in seen:
            continue
        seen.add(key)
        summaries.append(normalized)
    return summaries


def _producer_review_result(
    summaries: List[Dict[str, Any]],
) -> Dict[str, Any]:
    if not summaries:
        return {
            "review_state": None,
            "review_reason": None,
            "recommended_actions": [],
        }

    failing = [
        summary
        for summary in summaries
        if summary.get("passed") is False
        or summary.get("needs_revision")
        or summary.get("rewrite_recommended")
        or summary.get("needs_reference_analysis")
        or summary.get("review_state") in {"needs_revision", "needs_reference_analysis", "failed"}
    ]
    if not failing:
        return {
            "review_state": "passed",
            "review_reason": "producer_eval_passed",
            "recommended_actions": [],
        }

    needs_reference_analysis = any(
        summary.get("needs_reference_analysis") for summary in failing
    )
    rewrite_recommended = any(summary.get("rewrite_recommended") for summary in failing)
    actions: List[str] = []
    if needs_reference_analysis:
        _append_unique(actions, "attach_reference_analysis")
        _append_unique(actions, "ask_human_for_reference_cues")
    if rewrite_recommended:
        _append_unique(actions, "rewrite_storyboard_script_with_reference_cues")
    for summary in failing:
        for action in list(summary.get("recommended_actions") or []):
            _append_unique(actions, _clean_string(action))
    _append_unique(actions, "accept_with_risk")
    return {
        "review_state": (
            "needs_reference_analysis"
            if needs_reference_analysis
            else "needs_revision"
        ),
        "review_reason": "producer_eval_requires_review",
        "recommended_actions": actions,
    }


def _bounded_json(value: Any, *, limit: int = 12000) -> str:
    try:
        rendered = json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        rendered = str(value)
    if len(rendered) <= limit:
        return rendered
    return rendered[:limit] + "...<truncated>"


def _extract_json_object(text: Any) -> Dict[str, Any]:
    raw = str(text or "").strip()
    if not raw:
        return {}
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        pass

    start = raw.find("{")
    end = raw.rfind("}")
    if start < 0 or end <= start:
        return {}
    try:
        parsed = json.loads(raw[start : end + 1])
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _truthy(value: Any, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return default


def _quality_requirements_from_aol_metadata(
    request_contract_aol: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    metadata = _as_dict(request_contract_aol)
    return _as_dict(metadata.get("quality_requirements"))


def _rewrite_until_quality_passed(quality_requirements: Dict[str, Any]) -> bool:
    content_quality = _as_dict(quality_requirements.get("content_quality"))
    return _truthy(quality_requirements.get("rewrite_until_quality_passed")) or _truthy(
        content_quality.get("rewrite_until_quality_passed")
    )


def _producer_rewrite_dispatch_request(
    *,
    producer_eval_summaries: List[Dict[str, Any]],
    quality_requirements: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    request: Dict[str, Any] = {}
    for summary in producer_eval_summaries:
        candidate = _as_dict(
            summary.get("rewrite_dispatch_request")
            or summary.get("producer_rewrite_dispatch_request")
        )
        if _clean_string(candidate.get("playbook_code")):
            request = candidate
            break
    if not request:
        return None

    producer_eval_artifact_ids = [
        _clean_string(summary.get("artifact_id"))
        for summary in producer_eval_summaries
        if _clean_string(summary.get("artifact_id"))
    ]
    source_playbook_codes = [
        _clean_string(summary.get("playbook_code"))
        for summary in producer_eval_summaries
        if _clean_string(summary.get("playbook_code"))
    ]
    auto_allowed = _rewrite_until_quality_passed(quality_requirements)
    input_params = _as_dict(request.get("input_params"))
    input_params.update(
        {
            "quality_requirements": quality_requirements,
            "producer_eval_artifact_ids": producer_eval_artifact_ids,
            "source_playbook_codes": source_playbook_codes,
            "rewrite_handoff": {
                "value_from": "producer_quality_gate.rewrite_handoff"
            },
        }
    )
    return {
        **request,
        "schema_version": request.get("schema_version")
        or "producer_quality_rewrite_dispatch_request.v1",
        "dispatch_mode": (
            "auto_launch_allowed"
            if auto_allowed
            else "explicit_quality_requirement_required"
        ),
        "required_inputs": list(
            request.get("required_inputs")
            or [
                "storyboard",
                "reference_cue_map",
                "content_quality_eval",
                "quality_requirements",
                "rewrite_handoff",
            ]
        ),
        "input_params": input_params,
    }


def _producer_quality_gate_fallback(
    *,
    producer_review: Dict[str, Any],
    producer_eval_summaries: List[Dict[str, Any]],
    quality_requirements: Optional[Dict[str, Any]] = None,
    reason: Optional[str] = None,
) -> Dict[str, Any]:
    review_state = producer_review.get("review_state")
    recommended_actions = list(producer_review.get("recommended_actions") or [])
    needs_revision = review_state in {
        "needs_revision",
        "needs_reference_analysis",
        "failed",
    }
    gate_state = (
        "needs_reference_analysis"
        if review_state == "needs_reference_analysis"
        else "blocked_for_revision"
        if needs_revision
        else "passed"
    )
    quality_requirements_payload = _as_dict(quality_requirements)
    dispatch_request = (
        _producer_rewrite_dispatch_request(
            producer_eval_summaries=producer_eval_summaries,
            quality_requirements=quality_requirements_payload,
        )
        if needs_revision
        else None
    )
    return {
        "schema_version": "meeting_producer_quality_gate.v1",
        "gate_state": gate_state,
        "review_state": review_state,
        "review_reason": producer_review.get("review_reason"),
        "llm_review_status": "fallback" if needs_revision else "not_required",
        "llm_review_error": reason,
        "decision": (
            "reference_analysis_required"
            if review_state == "needs_reference_analysis"
            else "rewrite_required"
            if needs_revision
            else "accept"
        ),
        "completion_status": "needs_revision" if needs_revision else "accepted",
        "recommended_actions": recommended_actions,
        "rewrite_handoff": (
            {
                "kind": "producer_quality_rewrite_handoff",
                "source": "meeting_engine_runner",
                "target_review_state": review_state,
                "producer_eval_artifact_ids": [
                    summary.get("artifact_id")
                    for summary in producer_eval_summaries
                    if summary.get("artifact_id")
                ],
                "producer_eval_summaries": producer_eval_summaries,
                "required_actions": recommended_actions,
                "dispatch_request": dispatch_request,
            }
            if needs_revision
            else None
        ),
    }


def _normalize_meeting_quality_review(
    raw_review: Dict[str, Any],
    *,
    fallback_gate: Dict[str, Any],
) -> Dict[str, Any]:
    review = dict(raw_review or {})
    decision = _clean_string(review.get("decision")) or fallback_gate["decision"]
    if decision not in {
        "accept",
        "accept_with_risk",
        "rewrite_required",
        "reference_analysis_required",
        "human_review_required",
    }:
        decision = fallback_gate["decision"]

    actions = list(fallback_gate.get("recommended_actions") or [])
    for action in list(review.get("recommended_actions") or []):
        _append_unique(actions, _clean_string(action))

    gate_state = fallback_gate["gate_state"]
    if decision in {"rewrite_required", "human_review_required"}:
        gate_state = "blocked_for_revision"
    elif decision == "reference_analysis_required":
        gate_state = "needs_reference_analysis"
    elif decision == "accept_with_risk":
        gate_state = "accept_with_risk"
    elif decision == "accept":
        gate_state = "passed"

    rewrite_handoff = fallback_gate.get("rewrite_handoff")
    if isinstance(rewrite_handoff, dict):
        rewrite_handoff = {
            **rewrite_handoff,
            "meeting_review": {
                "decision": decision,
                "rationale": _clean_string(review.get("rationale")),
                "rewrite_instructions": review.get("rewrite_instructions") or [],
                "required_reference_questions": review.get(
                    "required_reference_questions"
                )
                or [],
            },
            "required_actions": actions,
        }

    return {
        **fallback_gate,
        "gate_state": gate_state,
        "llm_review_status": "completed",
        "llm_review_error": None,
        "decision": decision,
        "completion_status": (
            "accepted"
            if decision == "accept"
            else "accepted_with_risk"
            if decision == "accept_with_risk"
            else "needs_revision"
        ),
        "recommended_actions": actions,
        "rationale": _clean_string(review.get("rationale")),
        "rewrite_instructions": review.get("rewrite_instructions") or [],
        "required_reference_questions": review.get("required_reference_questions") or [],
        "rewrite_handoff": rewrite_handoff,
    }


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
        dispatch_artifacts = await self._dispatch_artifact_refs(
            meeting_result.dispatch_result,
            artifacts_store=getattr(self.store, "artifacts", None),
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
        if producer_review["review_state"] is None and meeting_result.completion_status:
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

    async def _producer_quality_gate_review(
        self,
        *,
        engine: Any,
        producer_review: Dict[str, Any],
        producer_eval_summaries: List[Dict[str, Any]],
        request_contract_aol: Dict[str, Any],
        task_ir_artifacts: List[Dict[str, Any]],
        user_message: str,
    ) -> Dict[str, Any]:
        quality_requirements = _quality_requirements_from_aol_metadata(
            request_contract_aol
        )
        fallback_gate = _producer_quality_gate_fallback(
            producer_review=producer_review,
            producer_eval_summaries=producer_eval_summaries,
            quality_requirements=quality_requirements,
        )
        if fallback_gate["gate_state"] == "passed":
            return fallback_gate

        generate_text = getattr(engine, "_generate_text", None)
        if not callable(generate_text):
            return _producer_quality_gate_fallback(
                producer_review=producer_review,
                producer_eval_summaries=producer_eval_summaries,
                quality_requirements=quality_requirements,
                reason="meeting_llm_review_unavailable",
            )

        messages = [
            {
                "role": "system",
                "content": (
                    "You are the MeetingEngine producer-quality reviewer. "
                    "Decide whether the produced storyboard can be accepted, "
                    "accepted with explicit risk, requires rewrite, requires "
                    "reference analysis, or requires human review. Return JSON only."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Review this producer evaluator result and choose the next "
                    "orchestration action.\n\n"
                    f"Original user instruction:\n{user_message}\n\n"
                    f"AOL/request contract metadata:\n{_bounded_json(request_contract_aol)}\n\n"
                    f"Producer review rollup:\n{_bounded_json(producer_review)}\n\n"
                    f"Producer eval summaries:\n{_bounded_json(producer_eval_summaries)}\n\n"
                    f"TaskIR artifacts:\n{_bounded_json(task_ir_artifacts, limit=8000)}\n\n"
                    "Return this JSON shape exactly:\n"
                    "{\n"
                    '  "decision": "accept|accept_with_risk|rewrite_required|reference_analysis_required|human_review_required",\n'
                    '  "rationale": "short reason",\n'
                    '  "recommended_actions": ["action_id"],\n'
                    '  "rewrite_instructions": ["concrete per-scene/content rewrite instruction"],\n'
                    '  "required_reference_questions": ["question if reference evidence is missing"]\n'
                    "}\n"
                    "Do not rewrite the full storyboard here. Produce routing "
                    "instructions for the next pass."
                ),
            },
        ]
        try:
            review_text = await generate_text(
                messages,
                max_tokens=1200,
                capability_profile="precise",
            )
        except TypeError:
            try:
                review_text = await generate_text(messages)
            except Exception as exc:
                return _producer_quality_gate_fallback(
                    producer_review=producer_review,
                    producer_eval_summaries=producer_eval_summaries,
                    quality_requirements=quality_requirements,
                    reason=str(exc),
                )
        except Exception as exc:
            return _producer_quality_gate_fallback(
                producer_review=producer_review,
                producer_eval_summaries=producer_eval_summaries,
                quality_requirements=quality_requirements,
                reason=str(exc),
            )

        parsed = _extract_json_object(review_text)
        if not parsed:
            return _producer_quality_gate_fallback(
                producer_review=producer_review,
                producer_eval_summaries=producer_eval_summaries,
                quality_requirements=quality_requirements,
                reason="meeting_llm_review_non_json",
            )
        return _normalize_meeting_quality_review(
            parsed,
            fallback_gate=fallback_gate,
        )

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
        for attempt_index in range(16):
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
            "producer_eval_summaries": [],
            "review_state": None,
            "review_reason": None,
            "recommended_actions": [],
            "request_contract_aol_metadata": self._request_contract_aol_metadata(session),
            "request_contract_aol_metadata_persisted": False,
            "missing_dependency": dependency,
            "error": message,
        }
