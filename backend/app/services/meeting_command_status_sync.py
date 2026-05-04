"""Best-effort Meeting Workbench command-ledger status sync from runtime tasks."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from backend.app.models.meeting_command import MeetingCommandStatus

logger = logging.getLogger(__name__)

SUCCESS_TASK_STATUSES = {"succeeded"}
FAILED_TASK_STATUSES = {"failed", "cancelled_by_user", "expired"}
RUNNING_TASK_STATUSES = {"running"}
ACCEPTED_TASK_STATUSES = {"pending"}


def _raw_status(status: Any) -> str:
    if hasattr(status, "value"):
        return str(status.value).strip().lower()
    return str(status or "").strip().lower()


def map_task_status_to_command_status(status: Any) -> Optional[MeetingCommandStatus]:
    """Map workspace task statuses onto the durable command lifecycle."""

    raw = _raw_status(status)
    if raw in SUCCESS_TASK_STATUSES:
        return MeetingCommandStatus.COMPLETED
    if raw in FAILED_TASK_STATUSES:
        return MeetingCommandStatus.FAILED
    if raw in RUNNING_TASK_STATUSES:
        return MeetingCommandStatus.RUNNING
    if raw in ACCEPTED_TASK_STATUSES:
        return MeetingCommandStatus.ACCEPTED
    return None


def _read_mapping(value: Any, key: str) -> Any:
    if isinstance(value, dict):
        return value.get(key)
    return None


def _first_text(*values: Any) -> Optional[str]:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _find_command_id(value: Any, *, depth: int = 0) -> Optional[str]:
    if depth > 5:
        return None
    if not isinstance(value, dict):
        return None
    direct = _first_text(
        value.get("command_id"),
        value.get("meeting_command_id"),
    )
    if direct:
        return direct
    for key in (
        "request_context",
        "action_params",
        "inputs",
        "input_params",
        "params",
        "object_action_plan",
        "command",
        "metadata",
    ):
        nested = _find_command_id(_read_mapping(value, key), depth=depth + 1)
        if nested:
            return nested
    return None


def extract_command_id_from_task(task: Any) -> Optional[str]:
    """Find the command id carried by a task's runtime payloads."""

    return _first_text(
        _find_command_id(getattr(task, "params", None)),
        _find_command_id(getattr(task, "result", None)),
        _find_command_id(getattr(task, "execution_context", None)),
    )


def extract_command_id_from_runtime_payload(*payloads: Any) -> Optional[str]:
    """Find a meeting command id in transport/result payloads."""

    for payload in payloads:
        command_id = _find_command_id(payload)
        if command_id:
            return command_id
    return None


def _find_aol_metadata(value: Any, *, depth: int = 0) -> Dict[str, Any]:
    if depth > 5 or not isinstance(value, dict):
        return {}
    direct = value.get("addressable_object_layer")
    if isinstance(direct, dict) and direct:
        return dict(direct)
    request_contract = value.get("request_contract")
    if isinstance(request_contract, dict):
        nested = _find_aol_metadata(request_contract, depth=depth + 1)
        if nested:
            return nested
    for key in ("metadata", "context", "inputs", "input_params", "params"):
        nested = _find_aol_metadata(_read_mapping(value, key), depth=depth + 1)
        if nested:
            return nested
    return {}


def _raw_result_status(result: Any, explicit_status: Any = None) -> str:
    if explicit_status is not None:
        return _raw_status(explicit_status)
    if isinstance(result, dict):
        return _raw_status(result.get("status"))
    return ""


def _status_from_runtime_result(
    result: Any,
    *,
    explicit_status: Any = None,
    governance_result: Any = None,
) -> Optional[MeetingCommandStatus]:
    raw = _raw_result_status(result, explicit_status)
    if raw in {"completed", "succeeded", "success"}:
        return MeetingCommandStatus.COMPLETED
    if raw in {"failed", "error", "timeout", "cancelled", "cancelled_by_user"}:
        return MeetingCommandStatus.FAILED
    if isinstance(governance_result, dict) and governance_result.get("success") is True:
        return MeetingCommandStatus.COMPLETED
    if raw in RUNNING_TASK_STATUSES:
        return MeetingCommandStatus.RUNNING
    if raw in ACCEPTED_TASK_STATUSES:
        return MeetingCommandStatus.ACCEPTED
    return None


def _artifact_refs_for_execution(
    execution_id: Optional[str],
    governance_result: Any,
) -> tuple[list[str], list[str]]:
    artifact_ids: list[str] = []
    artifact_paths: list[str] = []
    if isinstance(governance_result, dict):
        artifact_id = governance_result.get("artifact_id")
        if isinstance(artifact_id, str) and artifact_id.strip():
            artifact_ids.append(artifact_id.strip())

    if execution_id:
        try:
            from backend.app.services.stores.postgres.artifacts_store import (
                PostgresArtifactsStore,
            )

            artifact = PostgresArtifactsStore().get_by_execution_id(execution_id)
            if artifact is not None:
                artifact_id = getattr(artifact, "id", None)
                if isinstance(artifact_id, str) and artifact_id not in artifact_ids:
                    artifact_ids.append(artifact_id)
                storage_ref = getattr(artifact, "storage_ref", None)
                if isinstance(storage_ref, str) and storage_ref.strip():
                    artifact_paths.append(storage_ref.strip())
        except Exception:
            logger.debug(
                "Meeting command artifact lookup skipped for execution %s",
                execution_id,
                exc_info=True,
            )
    return artifact_ids, artifact_paths


def _producer_quality_from_runtime_payloads(
    *,
    existing_orchestration: Dict[str, Any],
    result: Any,
    governance_result: Any,
) -> Dict[str, Any]:
    try:
        from backend.app.services.orchestration.meeting.meeting_engine_runner import (
            _producer_eval_summaries_from_value,
            _producer_quality_gate_fallback,
            _producer_review_result,
        )
    except Exception:
        return {}

    summaries = [
        item
        for item in list(existing_orchestration.get("producer_eval_summaries") or [])
        if isinstance(item, dict)
    ]
    for payload, source in (
        (result, "late_agent_result"),
        (governance_result, "late_governance_result"),
    ):
        summaries.extend(_producer_eval_summaries_from_value(payload, source=source))

    if not summaries:
        return {}

    producer_review = _producer_review_result(summaries)
    producer_quality_gate = existing_orchestration.get("producer_quality_gate")
    if not isinstance(producer_quality_gate, dict) or producer_review.get(
        "review_state"
    ) in {"needs_revision", "needs_reference_analysis", "failed"}:
        producer_quality_gate = _producer_quality_gate_fallback(
            producer_review=producer_review,
            producer_eval_summaries=summaries,
            reason="late_result_meeting_llm_review_not_run",
        )
    return {
        "producer_eval_summaries": summaries,
        "review_state": producer_review.get("review_state"),
        "review_reason": producer_review.get("review_reason"),
        "recommended_actions": producer_review.get("recommended_actions") or [],
        "producer_quality_gate": producer_quality_gate,
        "completion_status": producer_quality_gate.get(
            "completion_status",
            existing_orchestration.get("completion_status"),
        ),
    }


def _task_runtime_id(task: Any) -> Optional[str]:
    return _first_text(getattr(task, "execution_id", None), getattr(task, "id", None))


def _iso_or_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _is_meeting_orchestration_command(command: Any) -> bool:
    metadata = getattr(command, "metadata", None)
    if not isinstance(metadata, dict):
        return False
    if metadata.get("dispatch_mode") == "route_meeting_orchestration":
        return True
    meeting_orchestration = metadata.get("meeting_orchestration")
    return isinstance(meeting_orchestration, dict)


def _agent_result_can_update_command(
    *,
    command: Any,
    execution_id: Optional[str],
    existing_orchestration: Dict[str, Any],
) -> bool:
    if not _is_meeting_orchestration_command(command):
        return True

    runtime_id = _first_text(execution_id)
    accepted_task_id = _first_text(getattr(command, "accepted_task_id", None))
    if runtime_id and accepted_task_id and runtime_id == accepted_task_id:
        return True

    return (
        runtime_id is not None
        and existing_orchestration.get("late_result_possible") is True
        and existing_orchestration.get("error_code") == "meeting_orchestration_timeout"
    )


def sync_meeting_command_from_task(task: Any, *, store: Any = None):
    """Best-effort sync of one task status into the meeting command ledger."""

    command_id = extract_command_id_from_task(task)
    if not command_id:
        return None
    command_status = map_task_status_to_command_status(getattr(task, "status", None))
    if command_status is None:
        return None

    if store is None:
        from backend.app.services.stores.meeting_command_store import (
            MeetingCommandStore,
        )

        store = MeetingCommandStore()

    command = store.get(command_id)
    if command is None:
        return None

    runtime_id = _task_runtime_id(task)
    if _is_meeting_orchestration_command(command):
        # MeetingEngine commands own their lifecycle at the orchestration layer.
        # Internal phase/playbook tasks may carry command_id for provenance, but
        # they must not demote the parent command after orchestration completes.
        if not runtime_id or runtime_id != command.accepted_task_id:
            return None

    accepted_task_id = command.accepted_task_id
    if runtime_id and (not accepted_task_id or accepted_task_id == command.command_id):
        accepted_task_id = runtime_id

    raw_status = _raw_status(getattr(task, "status", None))
    command.status = command_status
    command.accepted_task_id = accepted_task_id
    command.metadata = {
        **command.metadata,
        "dispatch_status": (
            "completed"
            if command_status == MeetingCommandStatus.COMPLETED
            else "failed"
            if command_status == MeetingCommandStatus.FAILED
            else raw_status
        ),
        "runtime_task": {
            "task_id": getattr(task, "id", None),
            "execution_id": getattr(task, "execution_id", None),
            "status": raw_status,
            "pack_id": getattr(task, "pack_id", None),
            "task_type": getattr(task, "task_type", None),
            "completed_at": _iso_or_none(getattr(task, "completed_at", None)),
            "error": getattr(task, "error", None),
        },
    }
    return store.save(command)


def sync_meeting_command_from_task_safely(task: Any) -> None:
    """Never let ledger sync failures break task status updates."""

    try:
        sync_meeting_command_from_task(task)
    except Exception as exc:
        logger.debug("Meeting command status sync skipped: %s", exc, exc_info=True)


def sync_meeting_command_from_agent_result(
    *,
    execution_id: Optional[str],
    result: Dict[str, Any],
    governance_result: Optional[Dict[str, Any]] = None,
    status: Any = None,
    store: Any = None,
):
    """Best-effort sync of late external-agent results into command ledger rows."""

    command_id = extract_command_id_from_runtime_payload(
        result,
        result.get("metadata") if isinstance(result, dict) else None,
        result.get("context") if isinstance(result, dict) else None,
        governance_result,
    )
    if not command_id:
        return None

    command_status = _status_from_runtime_result(
        result,
        explicit_status=status,
        governance_result=governance_result,
    )
    if command_status is None:
        return None

    if store is None:
        from backend.app.services.stores.meeting_command_store import (
            MeetingCommandStore,
        )

        store = MeetingCommandStore()

    command = store.get(command_id)
    if command is None:
        return None

    metadata = dict(command.metadata or {})
    existing_orchestration = metadata.get("meeting_orchestration")
    if not isinstance(existing_orchestration, dict):
        existing_orchestration = {}
    if not _agent_result_can_update_command(
        command=command,
        execution_id=execution_id,
        existing_orchestration=existing_orchestration,
    ):
        return None

    artifact_ids, artifact_paths = _artifact_refs_for_execution(
        execution_id,
        governance_result,
    )
    previous_error_code = existing_orchestration.get("error_code")
    recovered_from_timeout = previous_error_code == "meeting_orchestration_timeout"
    result_status = (
        "completed"
        if command_status == MeetingCommandStatus.COMPLETED
        else "failed"
        if command_status == MeetingCommandStatus.FAILED
        else _raw_result_status(result, status)
    )
    if artifact_ids:
        artifact_landing_status = "landed_late" if recovered_from_timeout else "landed"
    elif isinstance(governance_result, dict) and governance_result.get("success") is False:
        artifact_landing_status = "failed"
    else:
        artifact_landing_status = existing_orchestration.get(
            "artifact_landing_status",
            "pending",
        )

    aol_metadata = (
        existing_orchestration.get("request_contract_aol_metadata")
        if isinstance(existing_orchestration.get("request_contract_aol_metadata"), dict)
        else {}
    )
    if not aol_metadata:
        aol_metadata = _find_aol_metadata(result)
    if not aol_metadata:
        aol_metadata = _find_aol_metadata(metadata)
    producer_quality_update = _producer_quality_from_runtime_payloads(
        existing_orchestration=existing_orchestration,
        result=result,
        governance_result=governance_result,
    )

    updated_orchestration = {
        **existing_orchestration,
        "status": result_status,
        "completion_status": result_status,
        "external_execution_id": execution_id,
        "dispatch_result": result,
        "artifact_db_ids": artifact_ids
        or existing_orchestration.get("artifact_db_ids", []),
        "artifact_file_paths": artifact_paths
        or existing_orchestration.get("artifact_file_paths", []),
        "artifact_landing_status": artifact_landing_status,
        "request_contract_aol_metadata": aol_metadata,
        "late_result_reconciled": recovered_from_timeout,
        **producer_quality_update,
    }
    if command_status == MeetingCommandStatus.COMPLETED:
        updated_orchestration.pop("error", None)
        updated_orchestration.pop("error_code", None)
        if previous_error_code:
            updated_orchestration["recovered_from_error_code"] = previous_error_code
    elif isinstance(result, dict):
        error = result.get("error")
        if error:
            updated_orchestration["error"] = error

    command.status = command_status
    if execution_id:
        command.accepted_task_id = execution_id
    command.metadata = {
        **metadata,
        "dispatch_status": (
            "completed_late"
            if command_status == MeetingCommandStatus.COMPLETED
            and recovered_from_timeout
            else result_status
        ),
        "meeting_orchestration": updated_orchestration,
        "runtime_task": {
            "execution_id": execution_id,
            "status": _raw_result_status(result, status),
            "artifact_ids": artifact_ids,
        },
    }
    return store.save(command)


def sync_meeting_command_from_agent_result_safely(
    *,
    execution_id: Optional[str],
    result: Dict[str, Any],
    governance_result: Optional[Dict[str, Any]] = None,
    status: Any = None,
) -> None:
    """Never let late-result ledger reconciliation break result landing."""

    try:
        sync_meeting_command_from_agent_result(
            execution_id=execution_id,
            result=result,
            governance_result=governance_result,
            status=status,
        )
    except Exception as exc:
        logger.debug(
            "Meeting command late-result sync skipped: %s",
            exc,
            exc_info=True,
        )
