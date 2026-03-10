"""
Chat Session Setup

Unified session initialization for all chat paths (streaming generator,
background ChatOrchestratorService, legacy orchestrator). Eliminates
duplication of profile resolution, project detection, thread setup,
user event creation, runtime profile loading, and mode resolution.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from backend.app.models.mindscape import MindEvent, EventType, EventActor
from backend.app.models.workspace import Workspace

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


@dataclass
class ChatSession:
    """Resolved chat session context."""

    profile: Optional[Any]
    project_id: Optional[str]
    thread_id: str
    user_event: MindEvent
    runtime_profile: Any
    execution_mode: str
    locale: str


def get_or_create_default_thread(workspace_id: str, store) -> str:
    """
    Get or create default conversation thread for a workspace.

    Args:
        workspace_id: Workspace ID.
        store: MindscapeStore instance.

    Returns:
        Thread ID (default thread).
    """
    default_thread = store.conversation_threads.get_default_thread(workspace_id)
    if default_thread:
        return default_thread.id

    from backend.app.models.workspace import ConversationThread

    thread_id = str(uuid.uuid4())
    now_utc = _utc_now()
    default_thread = ConversationThread(
        id=thread_id,
        workspace_id=workspace_id,
        title="Default Conversation",
        project_id=None,
        pinned_scope=None,
        created_at=now_utc,
        updated_at=now_utc,
        last_message_at=now_utc,
        message_count=0,
        metadata={},
        is_default=True,
    )
    store.conversation_threads.create_thread(default_thread)
    logger.info("Created default thread %s for workspace %s", thread_id, workspace_id)
    return thread_id


def smart_truncate_message(message: str, max_length: int = 60) -> str:
    """
    Truncate message intelligently at sentence boundary.

    Args:
        message: Original message.
        max_length: Maximum length for preview.

    Returns:
        Truncated message with ellipsis if needed.
    """
    if len(message) <= max_length:
        return message

    for delimiter in [".", "!", "?", "\n"]:
        idx = message.find(delimiter, 0, max_length)
        if idx > 0:
            return message[: idx + 1] + "..."

    for delimiter in [",", " "]:
        idx = message.rfind(delimiter, 0, max_length)
        if idx > max_length * 0.5:
            return message[:idx] + "..."

    return message[:max_length] + "..."


async def setup_chat_session(
    request: Any,
    workspace: Workspace,
    workspace_id: str,
    profile_id: str,
    store: Any,
    user_event_id: Optional[str] = None,
) -> ChatSession:
    """
    Unified chat session setup: resolve profile, detect project, ensure
    thread, create user event, load runtime profile, resolve execution mode.

    Args:
        request: WorkspaceChatRequest (must have .message, .files, .mode,
                 .thread_id, .project_id).
        workspace: Workspace object.
        workspace_id: Workspace ID.
        profile_id: Profile ID.
        store: MindscapeStore instance.
        user_event_id: Optional pre-assigned user event ID.

    Returns:
        ChatSession with all resolved fields.
    """
    # 1. Resolve profile
    profile = None
    try:
        if profile_id:
            profile = await asyncio.to_thread(store.get_profile, profile_id)
    except Exception:
        pass

    # 2. Detect / resolve project
    from backend.app.services.project.project_creation_helper import (
        detect_and_create_project_if_needed,
    )

    requested_project_id = getattr(request, "project_id", None)
    project_id, _ = await detect_and_create_project_if_needed(
        message=request.message,
        workspace_id=workspace_id,
        profile_id=profile_id,
        store=store,
        workspace=workspace,
        existing_project_id=requested_project_id,
        create_on_medium_confidence=True,
    )

    # 3. Ensure thread
    thread_id = getattr(request, "thread_id", None)
    if not thread_id:
        thread_id = await asyncio.to_thread(
            get_or_create_default_thread, workspace_id, store
        )

    # 4. Create user event
    event_id = user_event_id or str(uuid.uuid4())
    user_event = MindEvent(
        id=event_id,
        timestamp=_utc_now(),
        actor=EventActor.USER,
        channel="local_workspace",
        profile_id=profile_id,
        project_id=project_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        event_type=EventType.MESSAGE,
        payload={
            "message": request.message,
            "files": getattr(request, "files", []) or [],
            "mode": getattr(request, "mode", "qa"),
        },
        entity_ids=[],
        metadata={},
    )
    await asyncio.to_thread(store.create_event, user_event)
    logger.info(
        "Created user event %s (project=%s, thread=%s)",
        user_event.id,
        project_id,
        thread_id,
    )

    # 5. Update thread stats
    from backend.app.services.conversation.thread_stats_updater import (
        update_thread_stats,
    )

    await update_thread_stats(store, workspace_id, thread_id)

    # 6. Load runtime profile and resolve execution mode
    from backend.app.services.stores.workspace_runtime_profile_store import (
        WorkspaceRuntimeProfileStore,
    )
    from backend.app.utils.runtime_profile import get_resolved_mode
    from backend.app.shared.i18n_loader import get_locale_from_context

    rt_store = WorkspaceRuntimeProfileStore(db_path=store.db_path)
    runtime_profile = await rt_store.get_runtime_profile(workspace_id)
    if not runtime_profile:
        runtime_profile = await rt_store.create_default_profile(workspace_id)

    resolved_mode_enum = get_resolved_mode(workspace, runtime_profile)
    execution_mode = (
        resolved_mode_enum.value
        if resolved_mode_enum
        else (getattr(workspace, "execution_mode", None) or "meeting")
    )

    locale = get_locale_from_context(profile=profile, workspace=workspace) or "zh-TW"

    return ChatSession(
        profile=profile,
        project_id=project_id,
        thread_id=thread_id,
        user_event=user_event,
        runtime_profile=runtime_profile,
        execution_mode=execution_mode,
        locale=locale,
    )
