"""MeetingEngine orchestration dispatch helpers for meeting commands."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from backend.app.models.meeting_command import (
    MeetingCommandEnvelope,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.workspace import Workspace
from backend.app.services.meeting_command_dispatch_routing import (
    _command_active_capability_code,
    command_instruction,
    meeting_orchestration_timeout_seconds,
)

logger = logging.getLogger(__name__)

TimeoutResolver = Callable[[MeetingCommandEnvelope | None], float]
OrchestrationDispatchHandler = Callable[..., Awaitable[tuple[MeetingCommandRecord, dict]]]


def _request_contract_aol_metadata(session: Any) -> dict:
    metadata = getattr(session, "metadata", None) or {}
    request_contract = metadata.get("request_contract")
    if not isinstance(request_contract, dict):
        return {}
    aol_metadata = request_contract.get("addressable_object_layer")
    return dict(aol_metadata) if isinstance(aol_metadata, dict) else {}


def _meeting_orchestration_timeout_result(
    *,
    session: Any,
    command: MeetingCommandRecord,
    timeout_seconds: float,
) -> dict:
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
        "artifact_landing_status": "pending",
        "late_result_possible": True,
        "timeout_seconds": timeout_seconds,
        "request_contract_aol_metadata": _request_contract_aol_metadata(session),
        "request_contract_aol_metadata_persisted": False,
        "error_code": "meeting_orchestration_timeout",
        "error": (
            "MeetingEngine orchestration timed out after "
            f"{timeout_seconds:.0f} seconds."
        ),
    }


async def _run_meeting_orchestration_in_background(
    *,
    command_id: str,
    canonical: MeetingCommandEnvelope,
    session: Any,
    workspace: Workspace,
    store: Any,
    session_store: Any,
    command_store: Any,
    workspace_id: str,
    dispatch_handler: OrchestrationDispatchHandler | None = None,
) -> None:
    """Run meeting orchestration in background and persist late command updates."""

    from backend.app.services.stores.meeting_command_store import MeetingCommandStore

    command_store = command_store or MeetingCommandStore()
    command = command_store.get(command_id)
    if command is None:
        return

    handler = dispatch_handler or dispatch_meeting_orchestration_for_command
    try:
        command, _ = await handler(
            command=command,
            canonical=canonical,
            session=session,
            workspace=workspace,
            store=store,
            session_store=session_store,
            workspace_id=workspace_id,
        )
    except Exception as exc:
        logger.exception(
            "Meeting orchestration background task failed for command %s",
            command_id,
        )
        command = command.model_copy(
            update={
                "status": MeetingCommandStatus.FAILED,
                "metadata": {
                    **command.metadata,
                    "dispatch_status": "failed",
                    "dispatch_error": str(exc),
                },
            }
        )
    command_store.save(command)


async def dispatch_meeting_orchestration_for_command(
    *,
    command: MeetingCommandRecord,
    canonical: MeetingCommandEnvelope,
    session: Any,
    workspace: Workspace,
    store: Any,
    session_store: Any,
    workspace_id: str,
    timeout_seconds_resolver: TimeoutResolver = meeting_orchestration_timeout_seconds,
) -> tuple[MeetingCommandRecord, dict]:
    from backend.app.services.object_runtime.aol_meeting_orchestration_bridge import (
        AOLMeetingOrchestrationBridge,
    )
    from backend.app.services.orchestration.meeting.meeting_engine_runner import (
        MeetingEngineRunner,
    )

    command.status = MeetingCommandStatus.RUNNING
    command.metadata = {
        **command.metadata,
        "dispatch_status": "running",
        "dispatch_mode": "route_meeting_orchestration",
    }
    active_capability_code = _command_active_capability_code(canonical)
    if active_capability_code:
        session.metadata = {
            **(getattr(session, "metadata", None) or {}),
            "active_capability_code": active_capability_code,
            "active_pack_code": active_capability_code,
        }
    bridge = AOLMeetingOrchestrationBridge()
    handoff_in = await bridge.build_handoff_in(
        command=command,
        canonical=canonical,
        session=session,
        workspace_id=workspace_id,
    )
    runner = MeetingEngineRunner(store=store, session_store=session_store)
    timeout_seconds = timeout_seconds_resolver(canonical)
    try:
        runner_result = await asyncio.wait_for(
            runner.run_meeting_orchestration(
                session=session,
                workspace=workspace,
                message=command_instruction(canonical),
                handoff_in=handoff_in,
                command=command,
            ),
            timeout=timeout_seconds,
        )
    except TimeoutError:
        logger.warning(
            "Meeting command orchestration timed out for %s after %.0fs",
            command.command_id,
            timeout_seconds,
        )
        runner_result = _meeting_orchestration_timeout_result(
            session=session,
            command=command,
            timeout_seconds=timeout_seconds,
        )
    command.accepted_task_id = runner_result.get("task_ir_id")
    command.status = (
        MeetingCommandStatus.COMPLETED
        if runner_result.get("status") == "completed"
        else MeetingCommandStatus.FAILED
    )
    command.metadata = {
        **command.metadata,
        "dispatch_status": runner_result.get("status", "failed"),
        "meeting_orchestration": runner_result,
    }
    return command, {"meeting_orchestration": runner_result}
