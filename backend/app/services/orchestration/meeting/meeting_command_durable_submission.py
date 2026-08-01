"""Durable meeting-command dispatch seam.

Meeting commands are first written to ``meeting_commands`` and then dispatched
through the canonical MeetingEngine function.  This module deliberately does
not schedule an in-process task: the ledger receipt is the durable boundary,
and a caller-owned worker queue is not introduced until a worker contract is
registered for this command family.
"""

from __future__ import annotations

from typing import Any

from backend.app.services.meeting_command_dispatch import (
    dispatch_meeting_orchestration_for_command,
)


async def dispatch_durable_meeting_command(
    *,
    command: Any,
    canonical: Any,
    session: Any,
    workspace: Any,
    store: Any,
    session_store: Any,
    workspace_id: str,
) -> tuple[Any, dict]:
    """Execute only after the command ledger row has been accepted.

    The result is still persisted by ``MeetingCommandSubmissionService``.  No
    FastAPI ``BackgroundTasks`` or ``asyncio.create_task`` is used, preventing
    request-lifetime work from disappearing on process restart.
    """

    return await dispatch_meeting_orchestration_for_command(
        command=command,
        canonical=canonical,
        session=session,
        workspace=workspace,
        store=store,
        session_store=session_store,
        workspace_id=workspace_id,
    )


__all__ = ["dispatch_durable_meeting_command"]
