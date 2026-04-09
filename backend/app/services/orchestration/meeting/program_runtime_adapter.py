"""
Program runtime adapter for promoting ProgramSpec into a durable ProgramRun.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.program_run import ProgramRun, ProgramRunStatus
from backend.app.models.program_spec import ProgramSpec
from backend.app.services.stores.program_run_store import ProgramRunStore

logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalize_string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    items: List[str] = []
    for raw in value:
        text = str(raw or "").strip()
        if text:
            items.append(text)
    return items


def _collect_phase_ids(dispatch_result: Optional[Dict[str, Any]]) -> tuple[list[str], list[str]]:
    completed_ids: list[str] = []
    failed_ids: list[str] = []
    phase_results = dispatch_result.get("phase_results") if isinstance(dispatch_result, dict) else None
    if not isinstance(phase_results, list):
        return completed_ids, failed_ids

    for phase_result in phase_results:
        if not isinstance(phase_result, dict):
            continue
        phase_id = str(
            phase_result.get("phase_id")
            or phase_result.get("id")
            or phase_result.get("source_intent_id")
            or ""
        ).strip()
        if not phase_id:
            continue
        status = str(phase_result.get("status") or "").strip().lower()
        if status in {"completed", "complete", "succeeded", "success"}:
            completed_ids.append(phase_id)
        elif status in {"failed", "aborted", "rejected", "cancelled"}:
            failed_ids.append(phase_id)
    return completed_ids, failed_ids


def _build_cursor_state(
    program_spec: ProgramSpec,
    *,
    meeting_session_id: str,
    dispatch_result: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    workstream_ids = [workstream.id for workstream in program_spec.workstreams]
    completed_ids, failed_ids = _collect_phase_ids(dispatch_result)
    remaining_ids = [
        workstream_id
        for workstream_id in workstream_ids
        if workstream_id not in completed_ids and workstream_id not in failed_ids
    ]
    return {
        "session_id": meeting_session_id,
        "workstream_ids": workstream_ids,
        "completed_workstream_ids": completed_ids,
        "failed_workstream_ids": failed_ids,
        "remaining_workstream_ids": remaining_ids,
        "remaining_work_count": len(remaining_ids),
        "recorded_at": _utc_now_iso(),
    }


def build_program_run_summary(program_run: ProgramRun) -> Dict[str, Any]:
    cursor_state = program_run.cursor_state if isinstance(program_run.cursor_state, dict) else {}
    return {
        "id": program_run.id,
        "meeting_session_id": program_run.meeting_session_id,
        "status": (
            program_run.status.value
            if hasattr(program_run.status, "value")
            else program_run.status
        ),
        "source": program_run.source,
        "scale": program_run.scale,
        "workstream_count": program_run.workstream_count,
        "milestone_count": program_run.milestone_count,
        "target_outputs": list(program_run.target_outputs or []),
        "remaining_work_count": int(cursor_state.get("remaining_work_count") or 0),
        "completed_work_count": len(
            _normalize_string_list(cursor_state.get("completed_workstream_ids"))
        ),
        "failed_work_count": len(
            _normalize_string_list(cursor_state.get("failed_workstream_ids"))
        ),
        "recorded_at": (
            program_run.recorded_at.isoformat()
            if getattr(program_run, "recorded_at", None)
            else None
        ),
    }


def _write_program_run_metadata(session: Any, program_run: ProgramRun) -> None:
    if session.metadata is None:
        session.metadata = {}
    session.metadata["program_run_id"] = program_run.id
    session.metadata["program_run_source"] = program_run.source
    session.metadata["program_run_status"] = (
        program_run.status.value
        if hasattr(program_run.status, "value")
        else program_run.status
    )
    session.metadata["program_run_recorded_at"] = (
        program_run.recorded_at.isoformat()
        if getattr(program_run, "recorded_at", None)
        else _utc_now_iso()
    )
    session.metadata["program_run_workstream_count"] = program_run.workstream_count
    session.metadata["program_run_milestone_count"] = program_run.milestone_count
    session.metadata["program_run_target_outputs"] = list(program_run.target_outputs or [])
    session.metadata["program_run_cursor_state"] = dict(program_run.cursor_state or {})
    session.metadata["program_run_summary"] = build_program_run_summary(program_run)


def record_session_program_run(
    meeting: Any,
    *,
    dispatch_result: Optional[Dict[str, Any]] = None,
) -> Optional[ProgramRun]:
    session = getattr(meeting, "session", None)
    if session is None:
        return None

    metadata = getattr(session, "metadata", None) or {}
    payload = metadata.get("last_program_spec")
    if not isinstance(payload, dict):
        return None

    try:
        program_spec = ProgramSpec.model_validate(payload)
    except Exception as exc:
        logger.warning("ProgramSpec metadata invalid for ProgramRun persistence: %s", exc)
        return None

    cursor_state = _build_cursor_state(
        program_spec,
        meeting_session_id=session.id,
        dispatch_result=dispatch_result,
    )
    status = (
        ProgramRunStatus.COMPLETED
        if cursor_state.get("remaining_work_count", 0) == 0
        else ProgramRunStatus.OPEN
    )
    source = str(metadata.get("last_program_spec_source") or "action_intent_bootstrap")
    existing_id = metadata.get("program_run_id")
    resolved_program_run_id = (
        str(existing_id).strip() if existing_id is not None else ""
    )
    store = ProgramRunStore()
    program_run = ProgramRun.new(
        workspace_id=session.workspace_id,
        meeting_session_id=session.id,
        project_id=session.project_id,
        thread_id=session.thread_id,
        status=status,
        source=source,
        scale=getattr(program_spec.scale, "value", program_spec.scale),
        program_spec=program_spec.model_dump(mode="json"),
        cursor_state=cursor_state,
        target_outputs=list(program_spec.target_outputs or []),
        metadata={
            "structured": source == "executor_structured",
            "meeting_status": (
                session.status.value if hasattr(session.status, "value") else session.status
            ),
            "meeting_round_count": getattr(session, "round_count", 0),
            "action_item_count": len(getattr(session, "action_items", []) or []),
            "last_program_spec_recorded_at": metadata.get("last_program_spec_recorded_at"),
        },
        program_run_id=resolved_program_run_id or None,
    )
    persisted = store.upsert_for_session(program_run)
    _write_program_run_metadata(session, persisted)
    try:
        meeting.session_store.update(session)
    except Exception as exc:
        logger.warning("Failed to persist session metadata after ProgramRun record: %s", exc)
    return persisted
