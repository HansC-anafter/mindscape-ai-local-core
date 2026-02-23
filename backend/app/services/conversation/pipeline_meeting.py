"""
Pipeline Meeting -- Meeting session lifecycle and TaskIR dispatch.

Handles meeting session creation, project meeting flag checking,
ExecutionLauncher setup, HandoffIn extraction, TaskIR persistence
and dispatch, and session finalization.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def build_execution_launcher(store: Any) -> Optional[Any]:
    """Build ExecutionLauncher for meeting action landing.

    Returns None on setup failure so meeting flow can degrade gracefully
    to task creation fallback.

    Args:
        store: MindscapeStore instance.

    Returns:
        ExecutionLauncher or None.
    """
    try:
        from backend.app.services.playbook_service import PlaybookService
        from backend.app.services.conversation.execution_launcher import (
            ExecutionLauncher,
        )

        playbook_service = PlaybookService(store=store)
        return ExecutionLauncher(playbook_service=playbook_service)
    except Exception as e:
        logger.warning(
            f"[PipelineCore] Failed to initialize ExecutionLauncher for meeting mode: {e}",
            exc_info=True,
        )
        return None


def extract_handoff_in(request: Optional[Any]) -> Optional[Any]:
    """Extract HandoffIn from request payload if present.

    Args:
        request: Original ChatRequest object.

    Returns:
        HandoffIn instance or None.
    """
    if not request:
        return None
    handoff_data = getattr(request, "handoff_in", None)
    if not handoff_data:
        return None
    from backend.app.models.handoff import HandoffIn

    if isinstance(handoff_data, dict):
        return HandoffIn(**handoff_data)
    if isinstance(handoff_data, HandoffIn):
        return handoff_data
    return None


async def persist_meeting_task_ir(task_ir: Any) -> None:
    """Persist compiled TaskIR with upsert semantics.

    Uses delete-then-create for full replacement to ensure
    governance, phases, and metadata are fully persisted.

    Args:
        task_ir: Compiled TaskIR from meeting engine.
    """
    try:
        from backend.app.services.stores.postgres.task_ir_store import (
            PostgresTaskIRStore,
        )

        store = PostgresTaskIRStore()
        replaced = store.replace_task_ir(task_ir)
        logger.info(
            "[PipelineCore] Persisted TaskIR %s (replaced=%s)",
            task_ir.task_id,
            replaced,
        )
    except Exception as e:
        logger.warning(
            "[PipelineCore] Failed to persist TaskIR: %s",
            e,
            exc_info=True,
        )


async def dispatch_task_ir(
    task_ir: Any,
    store: Any,
) -> Optional[Dict[str, Any]]:
    """Dispatch persisted TaskIR via HandoffHandler.

    Performs actuation plan lowering, then dispatches the first
    executable phase via HandoffHandler.

    Args:
        task_ir: Compiled and persisted TaskIR.
        store: MindscapeStore instance.

    Returns:
        Dispatch result dict or None on failure.
    """
    try:
        from backend.app.services.stores.postgres.task_ir_store import (
            PostgresTaskIRStore,
        )
        from backend.app.services.handoff_handler import HandoffHandler
        from backend.app.services.artifact_registry import ArtifactRegistry

        db_path = getattr(store, "db_path", None)
        if not db_path:
            return None

        ir_store = PostgresTaskIRStore()
        artifact_registry = ArtifactRegistry(db_path=db_path)
        handler = HandoffHandler(
            task_ir_store=ir_store,
            artifact_registry=artifact_registry,
        )

        # Lower phases to actuation plan
        task_ir.lower_to_actuation_plan()
        ir_store.replace_task_ir(task_ir)

        # Dispatch first executable phase
        first_phases = task_ir.get_next_executable_phases()
        if not first_phases:
            logger.info("[PipelineCore] No executable phases for %s", task_ir.task_id)
            return None

        engine = first_phases[0].preferred_engine or "playbook:generic"
        result = await handler.initiate_task_execution(task_ir, engine)
        logger.info(
            "[PipelineCore] Dispatched TaskIR %s via %s",
            task_ir.task_id,
            engine,
        )
        return result
    except Exception as e:
        logger.warning(
            "[PipelineCore] Dispatch failed for %s: %s",
            task_ir.task_id,
            e,
            exc_info=True,
        )
        return None


async def ensure_meeting_session(
    workspace_id: str,
    thread_id: str,
    session_store: Any,
    project_id: Optional[str] = None,
) -> Optional[Any]:
    """Get or create the active MeetingSession for this workspace/thread.

    - If an active session exists, reuse it.
    - If not, create a new one.

    Args:
        workspace_id: Workspace ID.
        thread_id: Thread ID.
        session_store: MeetingSessionStore instance.
        project_id: Optional project ID.

    Returns:
        MeetingSession or None on error.
    """
    try:
        loop = asyncio.get_running_loop()
        session = await loop.run_in_executor(
            None,
            lambda: session_store.get_active_session(
                workspace_id,
                project_id,
                thread_id,
            ),
        )
        if session:
            logger.info(f"[PipelineCore] Reusing active session {session.id}")
            return session

        # Create new session
        from backend.app.models.meeting_session import MeetingSession

        new_session = MeetingSession.new(
            workspace_id=workspace_id,
            project_id=project_id,
            thread_id=thread_id,
        )
        await loop.run_in_executor(
            None,
            lambda: session_store.create(new_session),
        )
        logger.info(f"[PipelineCore] Created new session {new_session.id}")
        return new_session
    except Exception as e:
        logger.warning(
            f"[PipelineCore] MeetingSession lifecycle error: {e}",
            exc_info=True,
        )
        return None


async def is_project_meeting_enabled(
    project_id: Optional[str],
    store: Any,
) -> bool:
    """Return whether persistent meeting is enabled on the project metadata.

    Args:
        project_id: Project ID.
        store: MindscapeStore instance.

    Returns:
        True if meeting mode is enabled.
    """
    if not project_id:
        return False
    try:
        loop = asyncio.get_running_loop()
        project = await loop.run_in_executor(
            None,
            lambda: store.get_project(project_id),
        )
        if not project:
            return False
        metadata = getattr(project, "metadata", {}) or {}
        raw = metadata.get("meeting_enabled")
        # Strict boolean: only True or "true" (not truthy strings like "1")
        return raw is True or (isinstance(raw, str) and raw.lower() == "true")
    except Exception as e:
        logger.warning(
            f"[PipelineCore] Failed to read project meeting flag: {e}",
            exc_info=True,
        )
        return False


async def finalize_meeting_session(
    result: Any,
    session_store: Any,
) -> None:
    """Record pipeline artifacts back to the MeetingSession.

    Links playbook execution ID and traces to the session record.
    Does NOT end the session -- that requires an explicit API call
    or idle timeout.

    Args:
        result: PipelineResult with meeting_session_id.
        session_store: MeetingSessionStore instance.
    """
    if not result.meeting_session_id:
        return

    try:
        loop = asyncio.get_running_loop()
        session = await loop.run_in_executor(
            None,
            lambda: session_store.get_by_id(result.meeting_session_id),
        )
        if not session:
            return

        # Append execution_id to decisions list if playbook was triggered
        if result.execution_id and result.execution_id not in session.decisions:
            session.decisions.append(result.execution_id)

        # Metadata enrichment
        run_meta = session.metadata.get("runs", [])
        run_meta.append(
            {
                "playbook": result.playbook_code,
                "execution_id": result.execution_id,
                "success": result.success,
                "error": result.error,
            }
        )
        session.metadata["runs"] = run_meta

        await loop.run_in_executor(
            None,
            lambda: session_store.update(session),
        )
        logger.info(
            f"[PipelineCore] Session {session.id} finalized "
            f"(decisions={len(session.decisions)})"
        )
    except Exception as e:
        logger.warning(
            f"[PipelineCore] Session finalize error: {e}",
            exc_info=True,
        )
