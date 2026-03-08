"""
Pipeline Meeting -- Meeting session lifecycle and TaskIR dispatch.

Handles meeting session creation, project meeting flag checking,
ExecutionLauncher setup, HandoffIn extraction, TaskIR persistence
and dispatch, and session finalization.
"""

import asyncio
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Agenda item constraints
_AGENDA_MAX_ITEMS = 10
_AGENDA_ITEM_MAX_LEN = 200


def _sanitize_agenda_item(msg: str) -> str:
    """Truncate and clean an agenda item."""
    clean = msg.strip()
    if len(clean) > _AGENDA_ITEM_MAX_LEN:
        clean = clean[:_AGENDA_ITEM_MAX_LEN] + "..."
    return clean


async def _decompose_agenda(
    user_message: str,
    model_name: str | None = None,
) -> list[str]:
    """Use LLM to decompose a user message into 2-5 agenda items.

    Falls back to [user_message] on any error.  Respects existing
    _AGENDA_MAX_ITEMS cap and _sanitize_agenda_item rules.

    Args:
        user_message: Raw user message to decompose.
        model_name: Optional model override.  Falls back to system
            setting ``chat_model`` if not provided.
    """
    if not user_message or len(user_message.strip()) < 10:
        return [_sanitize_agenda_item(user_message)]

    try:
        import inspect as _inspect
        import json as _json
        from backend.features.workspace.chat.utils.llm_provider import (
            get_llm_provider,
            get_llm_provider_manager,
        )

        if not model_name:
            from backend.app.services.system_settings_store import SystemSettingsStore

            try:
                setting = SystemSettingsStore().get_setting("chat_model")
                if setting and setting.value:
                    model_name = str(setting.value)
            except Exception:
                pass
        if not model_name:
            return [_sanitize_agenda_item(user_message)]

        manager = get_llm_provider_manager()
        provider, _ = get_llm_provider(
            model_name=model_name,
            llm_provider_manager=manager,
        )

        messages = [
            {
                "role": "system",
                "content": (
                    "Split the request into 2-5 short task labels (≤10 words each). "
                    "Return ONLY a JSON array of strings. Example: "
                    '["research X","create Y posts","find images"]'
                ),
            },
            {"role": "user", "content": user_message[:500]},
        ]
        # Provider-safe kwargs: filter by signature (Anthropic only
        # accepts messages+model, Vertex accepts temperature etc.)
        call_kwargs = {
            "messages": messages,
            "model": model_name,
            "temperature": 0.3,
            "max_tokens": 1024,
            "max_completion_tokens": 1024,
        }
        sig = _inspect.signature(provider.chat_completion)
        allowed = set(sig.parameters.keys())
        kwargs = {k: v for k, v in call_kwargs.items() if k in allowed}
        if "messages" not in kwargs:
            kwargs["messages"] = messages

        raw = await provider.chat_completion(**kwargs)
        # Parse JSON array from response
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1].rsplit("```", 1)[0].strip()
        # Handle incomplete JSON: find outermost [ ... ]
        start = text.find("[")
        end = text.rfind("]")
        if start >= 0 and end > start:
            text = text[start : end + 1]
        items = _json.loads(text)
        if isinstance(items, list) and 2 <= len(items) <= _AGENDA_MAX_ITEMS:
            return [_sanitize_agenda_item(str(i)) for i in items if str(i).strip()]
    except Exception as exc:
        logger.debug("Agenda decomposition failed (fallback): %s", exc)

    return [_sanitize_agenda_item(user_message)]


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

        ir_store = PostgresTaskIRStore()
        artifact_registry = ArtifactRegistry()
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
    user_message: Optional[str] = None,
    model_name: Optional[str] = None,
) -> Optional[Any]:
    """Get or create the active MeetingSession for this workspace/thread.

    - If an active session exists, reuse it (appending user_message to agenda).
    - If not, create a new one with user_message as initial agenda.

    Args:
        workspace_id: Workspace ID.
        thread_id: Thread ID.
        session_store: MeetingSessionStore instance.
        project_id: Optional project ID.
        user_message: Optional user message to include in agenda.
        model_name: Optional LLM model name for agenda decomposition.

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
            # Append user_message to agenda (dedup + cap)
            if user_message:
                decomposed = await _decompose_agenda(
                    user_message, model_name=model_name
                )
                current = list(session.agenda or [])
                for item in decomposed:
                    if (
                        item
                        and item not in current
                        and len(current) < _AGENDA_MAX_ITEMS
                    ):
                        current.append(item)
                if current != list(session.agenda or []):
                    session.agenda = current
                    try:
                        await loop.run_in_executor(
                            None,
                            lambda: session_store.update(session),
                        )
                    except Exception as exc:
                        logger.debug("Non-fatal agenda update: %s", exc)
            return session

        # Create new session with lens_id resolved from active preset
        from backend.app.models.meeting_session import MeetingSession

        lens_id = None
        try:
            from backend.app.services.stores.graph_store import GraphStore
            from backend.app.services.lens.effective_lens_resolver import (
                EffectiveLensResolver,
            )
            from backend.app.services.lens.session_override_store import (
                InMemorySessionStore,
            )

            graph_store = GraphStore()
            session_override_store = InMemorySessionStore()
            resolver = EffectiveLensResolver(graph_store, session_override_store)
            effective = resolver.resolve(
                profile_id="default-user",
                workspace_id=workspace_id,
            )
            lens_id = effective.global_preset_id
        except Exception as exc:
            logger.warning("[PipelineCore] Failed to resolve lens for session: %s", exc)

        initial_agenda = None
        if user_message:
            initial_agenda = await _decompose_agenda(
                user_message, model_name=model_name
            )
        new_session = MeetingSession.new(
            workspace_id=workspace_id,
            project_id=project_id,
            thread_id=thread_id,
            lens_id=lens_id,
            agenda=initial_agenda,
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

        # NOTE: Do NOT append execution_id to session.decisions.
        # session.decisions is reserved for DECISION_FINAL event IDs,
        # tracked via the event store. Mixing in execution_ids causes
        # semantic pollution (Pre-2 decision).

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
