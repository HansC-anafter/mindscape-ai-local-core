"""Meeting session lifecycle helpers for meeting pipeline runtime."""

import asyncio
import logging
from typing import Any, Awaitable, Callable, Optional

from backend.app.services.conversation.pipeline_meeting_core.agenda import (
    append_agenda_if_needed,
    decompose_agenda,
)

logger = logging.getLogger(__name__)


async def ensure_meeting_session(
    workspace_id: str,
    thread_id: str,
    session_store: Any,
    project_id: Optional[str] = None,
    user_message: Optional[str] = None,
    model_name: Optional[str] = None,
    executor_runtime: Optional[str] = None,
    explicit_session_id: Optional[str] = None,
    llm_generate_fn: Optional[Callable[..., Awaitable[str]]] = None,
) -> Optional[Any]:
    try:
        loop = asyncio.get_running_loop()
        if explicit_session_id:
            session = await loop.run_in_executor(
                None,
                lambda: session_store.get_by_id(explicit_session_id),
            )
            if not session:
                raise ValueError(f"Explicit meeting session not found: {explicit_session_id}")
            if session.workspace_id != workspace_id:
                raise ValueError(
                    f"Explicit meeting session workspace mismatch: {explicit_session_id}"
                )
            if not session.is_active:
                raise ValueError(f"Explicit meeting session is not active: {explicit_session_id}")
            if project_id and session.project_id and session.project_id != project_id:
                raise ValueError(
                    f"Explicit meeting session project mismatch: {explicit_session_id}"
                )

            changed = False
            if project_id and not session.project_id:
                session.project_id = project_id
                changed = True
            if thread_id and not session.thread_id:
                session.thread_id = thread_id
                changed = True
            elif thread_id and session.thread_id and session.thread_id != thread_id:
                raise ValueError(
                    f"Explicit meeting session thread mismatch: {explicit_session_id}"
                )
            if changed:
                await loop.run_in_executor(None, lambda: session_store.update(session))

            try:
                await append_agenda_if_needed(
                    session,
                    session_store,
                    user_message,
                    model_name=model_name,
                    executor_runtime=executor_runtime,
                    llm_generate_fn=llm_generate_fn,
                )
            except Exception as exc:
                logger.debug("Non-fatal explicit-session agenda update: %s", exc)
            logger.info(
                "[PipelineCore] Reusing explicit meeting session %s",
                session.id,
            )
            return session

        session = await loop.run_in_executor(
            None,
            lambda: session_store.get_active_session(
                workspace_id,
                project_id,
                thread_id,
            ),
        )
        if session:
            logger.info("[PipelineCore] Reusing active session %s", session.id)
            try:
                await append_agenda_if_needed(
                    session,
                    session_store,
                    user_message,
                    model_name=model_name,
                    executor_runtime=executor_runtime,
                    llm_generate_fn=llm_generate_fn,
                )
            except Exception as exc:
                logger.debug("Non-fatal agenda update: %s", exc)
            return session

        from backend.app.models.meeting_session import MeetingSession

        lens_id = _resolve_lens_id(workspace_id)
        initial_agenda = None
        if user_message:
            initial_agenda = await decompose_agenda(
                user_message,
                model_name=model_name,
                executor_runtime=executor_runtime,
                llm_generate_fn=llm_generate_fn,
            )
        new_session = MeetingSession.new(
            workspace_id=workspace_id,
            project_id=project_id,
            thread_id=thread_id,
            lens_id=lens_id,
            agenda=initial_agenda,
        )
        await loop.run_in_executor(None, lambda: session_store.create(new_session))
        logger.info("[PipelineCore] Created new session %s", new_session.id)
        return new_session
    except Exception as exc:
        logger.warning(
            "[PipelineCore] MeetingSession lifecycle error: %s",
            exc,
            exc_info=True,
        )
        return None


def _resolve_lens_id(workspace_id: str) -> Optional[str]:
    try:
        from backend.app.services.lens.effective_lens_resolver import (
            EffectiveLensResolver,
        )
        from backend.app.services.lens.session_override_store import (
            InMemorySessionStore,
        )
        from backend.app.services.stores.graph_store import GraphStore

        graph_store = GraphStore()
        session_override_store = InMemorySessionStore()
        resolver = EffectiveLensResolver(graph_store, session_override_store)
        effective = resolver.resolve(
            profile_id="default-user",
            workspace_id=workspace_id,
        )
        return effective.global_preset_id
    except Exception as exc:
        logger.warning("[PipelineCore] Failed to resolve lens for session: %s", exc)
        return None
