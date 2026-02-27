"""
PipelineCore Shim

Routes messages through PipelineCore when the feature flag is enabled,
then maps PipelineResult back to the legacy return contract expected
by API callers.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from backend.app.models.mindscape import MindEvent, EventActor, EventType
from backend.app.services.conversation.response_assembler import (
    serialize_events,
    collect_pending_tasks,
)

logger = logging.getLogger(__name__)


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


async def route_via_pipeline_core(
    store,
    workspace,
    workspace_id: str,
    profile_id: str,
    message: str,
    files: List[str],
    mode: str,
    project_id: Optional[str],
    thread_id: Optional[str],
    tasks_store,
    request: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Route a message through PipelineCore and map the result to the legacy
    return contract.

    This function encapsulates the entire PipelineCore shim path, including
    runtime profile resolution, user event creation, pipeline processing,
    and response mapping.

    Args:
        store: MindscapeStore instance.
        workspace: Workspace object.
        workspace_id: Workspace ID.
        profile_id: User profile ID.
        message: User message text.
        files: List of file IDs.
        mode: Interaction mode.
        project_id: Optional project ID.
        thread_id: Optional conversation thread ID.
        tasks_store: TasksStore instance.
        request: Optional original request object (forwarded to PipelineCore
                 for handoff/meeting data extraction).

    Returns:
        Response dict with workspace_id, display_events, triggered_playbook,
        pending_tasks, assistant_response, execution_id.
    """
    from backend.app.services.conversation.pipeline_core import PipelineCore
    from backend.app.services.stores.workspace_runtime_profile_store import (
        WorkspaceRuntimeProfileStore,
    )

    rt_store = WorkspaceRuntimeProfileStore()
    runtime_profile = await rt_store.get_runtime_profile(workspace_id)
    if not runtime_profile:
        runtime_profile = await rt_store.create_default_profile(workspace_id)

    profile = store.get_profile(profile_id)

    if not thread_id:
        from backend.features.workspace.chat.streaming.generator import (
            _get_or_create_default_thread,
        )

        thread_id = _get_or_create_default_thread(workspace_id, store)

    # Persist user event (legacy contract expects event chain)
    user_event_id = str(uuid.uuid4())
    user_event = MindEvent(
        id=user_event_id,
        timestamp=_utc_now(),
        actor=EventActor.USER,
        channel="local_workspace",
        profile_id=profile_id,
        workspace_id=workspace_id,
        thread_id=thread_id,
        event_type=EventType.MESSAGE,
        payload={"message": message},
        entity_ids=[],
        metadata={},
    )
    store.create_event(user_event)

    pipeline = PipelineCore(
        orchestrator_store=store,
        workspace=workspace,
        profile=profile,
        runtime_profile=runtime_profile,
    )
    result = await pipeline.process(
        workspace_id=workspace_id,
        profile_id=profile_id,
        thread_id=thread_id,
        project_id=project_id or "",
        message=message,
        user_event_id=user_event_id,
        execution_mode=mode,
        request=request,
    )

    # Map PipelineResult to legacy return contract
    triggered_playbook = None
    if result.playbook_code:
        triggered_playbook = {
            "playbook_code": result.playbook_code,
            "execution_id": result.execution_id,
            "status": "started" if result.execution_id else "failed",
            "context": {},
            "message": "",
        }

    # Collect pending tasks
    pending_tasks = []
    try:
        pending_tasks = collect_pending_tasks(tasks_store, workspace_id)
    except Exception as e:
        logger.debug("Shim pending_tasks fetch: %s", e)

    # Fetch display events from DB (matching legacy contract)
    display_events_dicts = []
    try:
        recent_events = store.get_events_by_workspace(workspace_id, limit=20)
        display_events_dicts = serialize_events(recent_events)
    except Exception as e:
        logger.debug("Shim display_events fetch: %s", e)

    return {
        "workspace_id": workspace_id,
        "display_events": display_events_dicts,
        "triggered_playbook": triggered_playbook,
        "pending_tasks": pending_tasks,
        "assistant_response": result.response_text,
        "execution_id": result.execution_id,
    }
