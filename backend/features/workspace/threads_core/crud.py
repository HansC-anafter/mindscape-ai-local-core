"""Conversation thread CRUD helpers."""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace import ConversationThread, Workspace
from backend.app.services.i18n_service import get_i18n_service
from backend.app.services.mindscape_store import MindscapeStore
from backend.features.workspace.threads_core.schemas import (
    CreateThreadRequest,
    UpdateThreadRequest,
)
from backend.features.workspace.threads_core.validation import get_thread_or_404

logger = logging.getLogger("backend.features.workspace.threads")


def _resolve_thread_title(request: CreateThreadRequest, store: MindscapeStore) -> str:
    title = request.title
    if title:
        return title

    if request.project_id:
        try:
            project = store.projects.get_project(request.project_id)
            if project:
                return f"與 {project.title} 的對話"
        except Exception as e:
            logger.warning(
                f"Failed to get project {request.project_id} for thread title: {e}"
            )

    return "新對話"


def _seed_welcome_message(
    *,
    workspace_id: str,
    thread_id: str,
    request: CreateThreadRequest,
    workspace: Workspace,
    store: MindscapeStore,
    now_utc: datetime,
) -> None:
    try:
        locale = workspace.default_locale or "zh-TW"
        i18n = get_i18n_service(default_locale=locale)
        welcome_message = i18n.t(
            "workspace", "welcome.returning_workspace", workspace_title=workspace.title
        )

        welcome_event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=now_utc,
            actor=EventActor.ASSISTANT,
            channel="local_workspace",
            profile_id=workspace.owner_user_id,
            project_id=request.project_id or workspace.primary_project_id,
            workspace_id=workspace_id,
            thread_id=thread_id,
            event_type=EventType.MESSAGE,
            payload={
                "message": welcome_message,
                "is_welcome": True,
                "suggestions": [
                    "suggestions.organize_tasks",
                    "suggestions.daily_planning",
                    "suggestions.view_progress",
                ],
            },
            entity_ids=[],
            metadata={"is_cold_start": False},
        )
        store.create_event(welcome_event)

        try:
            message_count = store.events.count_messages_by_thread(
                workspace_id=workspace_id,
                thread_id=thread_id,
            )
            store.conversation_threads.update_thread(
                thread_id=thread_id,
                last_message_at=now_utc,
                message_count=message_count,
            )
        except Exception as e:
            logger.warning(
                f"Failed to update thread statistics for seeded welcome message: {e}"
            )
    except Exception as e:
        logger.warning(
            f"Failed to seed welcome message for new thread {thread_id}: {e}"
        )


def create_thread_response(
    *,
    workspace_id: str,
    request: CreateThreadRequest,
    workspace: Workspace,
    store: MindscapeStore,
) -> ConversationThread:
    thread_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)
    title = _resolve_thread_title(request, store)

    thread = ConversationThread(
        id=thread_id,
        workspace_id=workspace_id,
        title=title,
        project_id=request.project_id,
        pinned_scope=request.pinned_scope,
        created_at=now_utc,
        updated_at=now_utc,
        last_message_at=now_utc,
        message_count=0,
        metadata={},
        is_default=False,
    )

    store.conversation_threads.create_thread(thread)
    _seed_welcome_message(
        workspace_id=workspace_id,
        thread_id=thread_id,
        request=request,
        workspace=workspace,
        store=store,
        now_utc=now_utc,
    )

    logger.info(f"Created conversation thread {thread_id} for workspace {workspace_id}")
    return thread


def list_threads_response(
    *,
    workspace_id: str,
    limit: Optional[int],
    store: MindscapeStore,
) -> list[ConversationThread]:
    return store.conversation_threads.list_threads_by_workspace(
        workspace_id=workspace_id, limit=limit
    )


def get_thread_response(
    *,
    workspace_id: str,
    thread_id: str,
    store: MindscapeStore,
) -> ConversationThread:
    return get_thread_or_404(store, workspace_id=workspace_id, thread_id=thread_id)


def update_thread_response(
    *,
    workspace_id: str,
    thread_id: str,
    request: UpdateThreadRequest,
    store: MindscapeStore,
) -> ConversationThread:
    get_thread_or_404(store, workspace_id=workspace_id, thread_id=thread_id)
    updated_thread = store.conversation_threads.update_thread(
        thread_id=thread_id,
        title=request.title,
        project_id=request.project_id,
        pinned_scope=request.pinned_scope,
    )
    if not updated_thread:
        raise HTTPException(status_code=500, detail="Failed to update thread")
    return updated_thread


def delete_thread_response(
    *,
    workspace_id: str,
    thread_id: str,
    store: MindscapeStore,
):
    thread = get_thread_or_404(store, workspace_id=workspace_id, thread_id=thread_id)
    if thread.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default thread")

    deleted = store.conversation_threads.delete_thread(thread_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete thread")

    return {"message": "Thread deleted successfully"}
