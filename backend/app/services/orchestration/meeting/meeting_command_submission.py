"""Submission service for Meeting Workbench command envelopes."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import BackgroundTasks

from backend.app.models.meeting_command import (
    MeetingCommandAcceptResponse,
    MeetingCommandEnvelope,
    MeetingCommandRecord,
    MeetingCommandStatus,
)
from backend.app.models.workspace import Workspace
from backend.app.services.conversation_orchestrator import ConversationOrchestrator
from backend.app.services.meeting_command_dispatch import (
    _run_meeting_orchestration_in_background,
    dispatch_chat_for_command,
    dispatch_client_action_for_command,
    dispatch_meeting_orchestration_for_command,
    dispatch_object_action_for_command,
    dispatch_playbook_for_command,
    should_route_chat,
    should_route_client_action,
    should_route_meeting_orchestration,
    should_route_object_action,
    should_route_playbook,
)
from backend.app.services.meeting_command_parser import (
    MeetingCommandNormalizationError,
    canonicalize_meeting_command_envelope,
)
from backend.app.services.meeting_command_client_action_events import (
    emit_meeting_client_action_ready_event,
)
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.stores.meeting_command_store import MeetingCommandStore
from backend.app.services.stores.meeting_session_store import MeetingSessionStore


def command_error_detail(code: str, message: str, **extra):
    return {"code": code, "message": message, **extra}


class MeetingCommandSubmissionError(Exception):
    """HTTP-safe command submission error."""

    def __init__(self, *, status_code: int, detail: dict[str, Any]) -> None:
        super().__init__(detail.get("message") or detail.get("code"))
        self.status_code = status_code
        self.detail = detail


_meeting_command_store: MeetingCommandStore | None = None
_meeting_session_store: MeetingSessionStore | None = None


def get_meeting_command_store() -> MeetingCommandStore:
    global _meeting_command_store
    if _meeting_command_store is None:
        _meeting_command_store = MeetingCommandStore()
    return _meeting_command_store


def get_meeting_session_store() -> MeetingSessionStore:
    global _meeting_session_store
    if _meeting_session_store is None:
        _meeting_session_store = MeetingSessionStore()
    return _meeting_session_store


def validate_path_identity(
    envelope: MeetingCommandEnvelope,
    *,
    workspace_id: str,
    meeting_id: str,
) -> None:
    if envelope.workspace_id and envelope.workspace_id != workspace_id:
        raise MeetingCommandSubmissionError(
            status_code=400,
            detail=command_error_detail(
                "workspace_mismatch",
                "Command envelope workspace_id must match the route workspace_id.",
            ),
        )
    if envelope.meeting_id != meeting_id:
        raise MeetingCommandSubmissionError(
            status_code=400,
            detail=command_error_detail(
                "meeting_mismatch",
                "Command envelope meeting_id must match the route meeting_id.",
            ),
        )


def validate_meeting_session(
    *,
    workspace_id: str,
    meeting_id: str,
    session_store: MeetingSessionStore | None = None,
):
    store = session_store or get_meeting_session_store()
    session = store.get_by_id(meeting_id)
    if session is None:
        raise MeetingCommandSubmissionError(
            status_code=404,
            detail=command_error_detail(
                "meeting_session_not_found",
                f"Meeting session '{meeting_id}' was not found.",
            ),
        )
    if session.workspace_id != workspace_id:
        raise MeetingCommandSubmissionError(
            status_code=404,
            detail=command_error_detail(
                "meeting_session_not_found",
                f"Meeting session '{meeting_id}' was not found in workspace '{workspace_id}'.",
            ),
        )
    return session


class MeetingCommandSubmissionService:
    """Submit meeting command envelopes through the canonical ledger path."""

    def __init__(
        self,
        *,
        command_store: MeetingCommandStore | None = None,
        session_store: MeetingSessionStore | None = None,
    ) -> None:
        self.command_store = command_store or get_meeting_command_store()
        self.session_store = session_store or get_meeting_session_store()

    async def submit_envelope(
        self,
        *,
        envelope: MeetingCommandEnvelope,
        workspace_id: str,
        meeting_id: str,
        workspace: Workspace,
        orchestrator: ConversationOrchestrator,
        mindscape_store: MindscapeStore,
        background_tasks: BackgroundTasks | None = None,
    ) -> MeetingCommandAcceptResponse:
        validate_path_identity(
            envelope,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
        )
        session = validate_meeting_session(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            session_store=self.session_store,
        )
        try:
            canonical = canonicalize_meeting_command_envelope(
                envelope,
                workspace_id=workspace_id,
                meeting_id=meeting_id,
            )
        except MeetingCommandNormalizationError as exc:
            raise MeetingCommandSubmissionError(
                status_code=422,
                detail=command_error_detail(
                    "invalid_command_reference",
                    "Meeting command contains invalid object references.",
                    errors=[
                        error.model_dump(exclude_none=True) for error in exc.errors
                    ],
                ),
            ) from exc

        now = datetime.now(timezone.utc)
        command_id = canonical.command_id or f"cmd_{uuid.uuid4().hex}"
        command = MeetingCommandRecord(
            command_id=command_id,
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            thread_id=canonical.thread_id or session.thread_id or meeting_id,
            client_draft_id=canonical.client_draft_id,
            origin_surface=canonical.origin_surface,
            actor=canonical.actor,
            intent_text=canonical.intent_text,
            context_objects=canonical.context_objects,
            requested_action=canonical.requested_action,
            expected_outputs=canonical.expected_outputs,
            write_mode=canonical.write_mode,
            status=MeetingCommandStatus.ACCEPTED,
            metadata={
                **canonical.metadata,
                "meeting_mentions": canonical.meeting_mentions,
                "dispatch_status": "pending_runtime_integration",
            },
            created_at=now,
            updated_at=now,
        )
        saved = self.command_store.save(command)
        dispatch_result = None

        if should_route_meeting_orchestration(canonical):
            try:
                if background_tasks is not None:
                    command = saved.model_copy(
                        update={
                            "status": MeetingCommandStatus.ACCEPTED,
                            "metadata": {
                                **saved.metadata,
                                "dispatch_status": "accepted",
                                "dispatch_mode": "route_meeting_orchestration",
                                "meeting_orchestration": {
                                    "status": "accepted",
                                    "completion_status": "accepted",
                                    "artifact_landing_status": "pending",
                                    "request_contract_aol_metadata": getattr(
                                        session, "metadata", {}
                                    ).get("request_contract", {})
                                    if isinstance(getattr(session, "metadata", None), dict)
                                    else {},
                                },
                            },
                        }
                    )
                    background_tasks.add_task(
                        _run_meeting_orchestration_in_background,
                        command_id=saved.command_id,
                        canonical=canonical,
                        session=session,
                        workspace=workspace,
                        store=mindscape_store,
                        session_store=self.session_store,
                        command_store=self.command_store,
                        workspace_id=workspace_id,
                    )
                    dispatch_result = {
                        "meeting_orchestration": {
                            "status": "accepted",
                            "artifact_landing_status": "pending",
                            "task_ir_id": None,
                        }
                    }
                    saved = command
                else:
                    command, dispatch_result = await dispatch_meeting_orchestration_for_command(
                        command=saved,
                        canonical=canonical,
                        session=session,
                        workspace=workspace,
                        store=mindscape_store,
                        session_store=self.session_store,
                        workspace_id=workspace_id,
                    )
                    saved = command
            except Exception as exc:
                saved = self._save_failed_command(saved, exc)
                raise
            saved = self.command_store.save(saved)
        elif should_route_client_action(canonical):
            try:
                command, dispatch_result = await dispatch_client_action_for_command(
                    command=saved,
                    canonical=canonical,
                )
                saved = self.command_store.save(command)
                emit_meeting_client_action_ready_event(
                    command=saved,
                    client_action=dispatch_result["client_action"],
                    workspace=workspace,
                    session=session,
                    mindscape_store=mindscape_store,
                )
            except Exception as exc:
                saved = self._save_failed_command(saved, exc)
                raise
        elif should_route_object_action(canonical):
            try:
                command, dispatch_result = await dispatch_object_action_for_command(
                    command=saved,
                    canonical=canonical,
                    workspace_id=workspace_id,
                    meeting_id=meeting_id,
                    session=session,
                )
            except Exception as exc:
                saved = self._save_failed_command(saved, exc)
                raise
            saved = self.command_store.save(command)
        elif should_route_playbook(canonical):
            try:
                command, dispatch_result = await dispatch_playbook_for_command(
                    command=saved,
                    canonical=canonical,
                    workspace=workspace,
                    orchestrator=orchestrator,
                    meeting_id=meeting_id,
                    session=session,
                )
            except Exception as exc:
                saved = self._save_failed_command(saved, exc)
                raise
            saved = self.command_store.save(command)
        elif should_route_chat(canonical):
            try:
                command, dispatch_result = await dispatch_chat_for_command(
                    command=saved,
                    canonical=canonical,
                    workspace=workspace,
                    orchestrator=orchestrator,
                    meeting_id=meeting_id,
                    session=session,
                    background_tasks=background_tasks,
                )
            except Exception as exc:
                saved = self._save_failed_command(saved, exc)
                raise
            saved = self.command_store.save(command)

        return MeetingCommandAcceptResponse(
            workspace_id=workspace_id,
            meeting_id=meeting_id,
            command_id=saved.command_id,
            status=saved.status,
            command=saved,
            dispatch_result=dispatch_result,
        )

    def _save_failed_command(
        self,
        command: MeetingCommandRecord,
        exc: Exception,
    ) -> MeetingCommandRecord:
        failed = command.model_copy(
            update={
                "status": MeetingCommandStatus.FAILED,
                "metadata": {
                    **command.metadata,
                    "dispatch_status": "failed",
                    "dispatch_error": str(exc),
                },
            }
        )
        return self.command_store.save(failed)


__all__ = [
    "MeetingCommandSubmissionError",
    "MeetingCommandSubmissionService",
    "command_error_detail",
    "get_meeting_command_store",
    "get_meeting_session_store",
    "validate_meeting_session",
    "validate_path_identity",
]
