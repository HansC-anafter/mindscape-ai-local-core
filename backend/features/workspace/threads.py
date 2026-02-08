"""
Workspace Threads Routes

Handles /workspaces/{id}/threads endpoints for conversation thread management.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Literal
from fastapi import APIRouter, HTTPException, Path, Body, Query, Depends

from backend.app.models.mindscape import MindEvent, EventActor, EventType
from backend.app.models.workspace import ConversationThread
from backend.app.routes.workspace_dependencies import get_workspace, get_store
from backend.app.models.workspace import Workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.app.services.i18n_service import get_i18n_service
from backend.app.models.thread_bundle import (
    ThreadBundle, ThreadOverview, ThreadDeliverable,
    ThreadReferenceResponse, ThreadRun, ThreadSource
)
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-threads"])
logger = logging.getLogger(__name__)


class CreateThreadRequest(BaseModel):
    """Request to create a new conversation thread"""
    title: Optional[str] = Field(None, description="Thread title (auto-generated if not provided)")
    project_id: Optional[str] = Field(None, description="Optional: associate with a project")
    pinned_scope: Optional[str] = Field(None, description="Optional: pin a scope for this thread")


class UpdateThreadRequest(BaseModel):
    """Request to update a conversation thread"""
    title: Optional[str] = Field(None, description="Thread title")
    project_id: Optional[str] = Field(None, description="Project ID")
    pinned_scope: Optional[str] = Field(None, description="Pinned scope")


@router.post("/{workspace_id}/threads", response_model=ConversationThread)
async def create_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: CreateThreadRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
) -> ConversationThread:
    """
    Create a new conversation thread in a workspace.
    """
    thread_id = str(uuid.uuid4())
    now_utc = datetime.now(timezone.utc)

    # 自動生成標題（如果沒有提供）
    title = request.title
    if not title:
        if request.project_id:
            try:
                project = store.projects.get_project(request.project_id)
                if project:
                    title = f"與 {project.title} 的對話"
            except Exception as e:
                logger.warning(f"Failed to get project {request.project_id} for thread title: {e}")

        if not title:
            title = "新對話"

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
        is_default=False
    )

    # 保存到資料庫
    store.conversation_threads.create_thread(thread)

    # Seed a welcome message so a new thread isn't an empty screen.
    try:
        locale = workspace.default_locale or "zh-TW"
        i18n = get_i18n_service(default_locale=locale)
        welcome_message = i18n.t("workspace", "welcome.returning_workspace", workspace_title=workspace.title)

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
                # Frontend renders these via i18n keys when present.
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

        # Update thread statistics after seeding the welcome message.
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
            logger.warning(f"Failed to update thread statistics for seeded welcome message: {e}")
    except Exception as e:
        logger.warning(f"Failed to seed welcome message for new thread {thread_id}: {e}")

    logger.info(f"Created conversation thread {thread_id} for workspace {workspace_id}")
    return thread


@router.get("/{workspace_id}/threads", response_model=List[ConversationThread])
async def list_threads(
    workspace_id: str = Path(..., description="Workspace ID"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Maximum number of threads to return"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
) -> List[ConversationThread]:
    """
    獲取 Workspace 的所有對話 Thread 列表

    返回按 updated_at DESC 排序的 thread 列表。
    """
    threads = store.conversation_threads.list_threads_by_workspace(
        workspace_id=workspace_id,
        limit=limit
    )
    return threads


@router.get("/{workspace_id}/threads/{thread_id}", response_model=ConversationThread)
async def get_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
) -> ConversationThread:
    """
    獲取指定的對話 Thread
    """
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Thread does not belong to this workspace")

    return thread


@router.put("/{workspace_id}/threads/{thread_id}", response_model=ConversationThread)
async def update_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    request: UpdateThreadRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
) -> ConversationThread:
    """
    更新對話 Thread 的標題或其他屬性
    """
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Thread does not belong to this workspace")

    updated_thread = store.conversation_threads.update_thread(
        thread_id=thread_id,
        title=request.title,
        project_id=request.project_id,
        pinned_scope=request.pinned_scope
    )

    if not updated_thread:
        raise HTTPException(status_code=500, detail="Failed to update thread")

    return updated_thread


@router.delete("/{workspace_id}/threads/{thread_id}")
async def delete_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    刪除對話 Thread

    注意：刪除 thread 不會刪除相關的 mind_events，它們的 thread_id 會保留。
    """
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Thread does not belong to this workspace")

    if thread.is_default:
        raise HTTPException(status_code=400, detail="Cannot delete default thread")

    deleted = store.conversation_threads.delete_thread(thread_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete thread")

    return {"message": "Thread deleted successfully"}


@router.get("/{workspace_id}/threads/{thread_id}/bundle", response_model=ThreadBundle)
async def get_thread_bundle(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
) -> ThreadBundle:
    """
    Get Thread Bundle (aggregated view)

    Data sources:
    - Deliverables: artifacts table (with thread_id)
    - References: thread_references table
    - Runs: playbook_executions table
    - Sources: thread configuration

    Note: Does not use events aggregation to avoid performance issues.
    """
    # Get thread basic info
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Thread does not belong to this workspace")

    # Get Deliverables from artifacts table
    artifacts = store.artifacts.get_by_thread(
        workspace_id=workspace_id,
        thread_id=thread_id,
        limit=100
    )
    deliverables = []
    for a in artifacts:
        # Infer source from playbook_code and metadata
        source = 'playbook' if a.playbook_code else 'ai_generated'
        if a.metadata and 'source' in a.metadata:
            source = a.metadata['source']

        # Get source_event_id from metadata or execution_id
        source_event_id = a.metadata.get('source_event_id', '') if a.metadata else ''
        if not source_event_id and a.execution_id:
            source_event_id = a.execution_id

        # Infer status from metadata or default to 'draft'
        status = a.metadata.get('status', 'draft') if a.metadata else 'draft'
        if a.sync_state == 'synced':
            status = 'final'

        deliverables.append(ThreadDeliverable(
            id=a.id,
            title=a.title or 'Untitled',
            artifact_type=a.artifact_type.value if hasattr(a.artifact_type, 'value') else str(a.artifact_type),
            source=source,
            source_event_id=source_event_id,
            status=status,
            updated_at=a.updated_at.isoformat() if a.updated_at else a.created_at.isoformat(),
        ))

    # Get References from thread_references table
    refs = store.thread_references.get_by_thread(
        workspace_id=workspace_id,
        thread_id=thread_id,
        limit=100
    )
    references = [
        ThreadReferenceResponse(
            id=r.id,
            source_type=r.source_type,
            uri=r.uri,
            title=r.title,
            snippet=r.snippet,
            reason=r.reason,
            created_at=r.created_at.isoformat(),
            pinned_by=r.pinned_by or 'user',
        )
        for r in refs
    ]

    # Get Runs from playbook_executions table
    executions = store.playbook_executions.get_by_thread(
        workspace_id=workspace_id,
        thread_id=thread_id,
        limit=20
    )
    runs = []
    for ex in executions:
        # Get deliverable IDs associated with this execution
        deliverable_ids = [a.id for a in artifacts if a.execution_id == ex.id]

        # Calculate steps from metadata or checkpoint
        steps_completed = 0
        steps_total = 0
        if ex.metadata:
            steps_completed = ex.metadata.get('steps_completed', 0)
            steps_total = ex.metadata.get('steps_total', 0)

        # Calculate duration
        duration_ms = None
        if ex.created_at and ex.updated_at:
            delta = ex.updated_at - ex.created_at
            duration_ms = int(delta.total_seconds() * 1000)

        runs.append(ThreadRun(
            id=ex.id,
            playbook_name=ex.playbook_code,
            status=ex.status,
            started_at=ex.created_at.isoformat(),
            duration_ms=duration_ms,
            steps_completed=steps_completed,
            steps_total=steps_total,
            deliverable_ids=deliverable_ids,
        ))

    # Get Sources from thread configuration
    sources = _get_thread_sources(thread, store)

    # Determine thread status
    status = 'in_progress'
    if deliverables and all(d.status == 'final' for d in deliverables):
        status = 'delivered'
    elif not deliverables and not references:
        status = 'pending_data'

    return ThreadBundle(
        thread_id=thread_id,
        overview=ThreadOverview(
            title=thread.title,
            status=status,
            summary=thread.metadata.get('summary') if thread.metadata else None,
            project_id=thread.project_id,
            pinned_scope=thread.pinned_scope,
        ),
        deliverables=deliverables,
        references=references,
        runs=runs,
        sources=sources,
    )


def _get_thread_sources(thread: ConversationThread, store: MindscapeStore) -> List[ThreadSource]:
    """
    Get thread sources from thread configuration

    Currently returns empty list. Future implementation can extract
    sources from pinned_scope or connected connectors.
    """
    sources = []

    # If thread has pinned_scope, convert it to ThreadSource
    if thread.pinned_scope:
        if isinstance(thread.pinned_scope, dict):
            scope_type = thread.pinned_scope.get('type', '')
            if scope_type == 'site':
                sources.append(ThreadSource(
                    id=thread.pinned_scope.get('identifier', ''),
                    type='wordpress_site',
                    identifier=thread.pinned_scope.get('identifier', ''),
                    display_name=thread.pinned_scope.get('display_name', ''),
                    permissions=['read', 'write'],
                    sync_status='connected'
                ))
            elif scope_type == 'obsidian_vault':
                sources.append(ThreadSource(
                    id=thread.pinned_scope.get('identifier', ''),
                    type='obsidian_vault',
                    identifier=thread.pinned_scope.get('identifier', ''),
                    display_name=thread.pinned_scope.get('display_name', ''),
                    permissions=['read', 'write'],
                    sync_status='connected'
                ))

    return sources


class AddReferenceRequest(BaseModel):
    """Request to add a reference to a thread"""
    source_type: Literal['obsidian', 'notion', 'wordpress', 'local_file', 'url', 'google_drive'] = Field(
        ..., description="Source connector type"
    )
    uri: str = Field(..., description="Real URI (clickable)")
    title: str = Field(..., description="Reference title")
    snippet: Optional[str] = Field(None, description="Short summary snippet")
    reason: Optional[str] = Field(None, description="Reason for pinning")


class UpdateReferenceRequest(BaseModel):
    """Request to update a thread reference"""
    title: Optional[str] = Field(None, description="Reference title")
    snippet: Optional[str] = Field(None, description="Short summary snippet")
    reason: Optional[str] = Field(None, description="Reason for pinning")


@router.post("/{workspace_id}/threads/{thread_id}/references", response_model=ThreadReferenceResponse)
async def add_reference_to_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    request: AddReferenceRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
) -> ThreadReferenceResponse:
    """
    Add a reference to a thread

    Pins an external resource (Obsidian note, Notion page, WordPress post,
    local file, URL) as a thread reference.
    """
    # Verify thread exists and belongs to workspace
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Thread does not belong to this workspace")

    from backend.app.models.workspace import ThreadReference

    reference = ThreadReference(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        thread_id=thread_id,
        source_type=request.source_type,
        uri=request.uri,
        title=request.title,
        snippet=request.snippet,
        reason=request.reason,
        pinned_by='user',
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )

    created_reference = store.thread_references.create_reference(reference)

    return ThreadReferenceResponse(
        id=created_reference.id,
        source_type=created_reference.source_type,
        uri=created_reference.uri,
        title=created_reference.title,
        snippet=created_reference.snippet,
        reason=created_reference.reason,
        created_at=created_reference.created_at.isoformat(),
        pinned_by=created_reference.pinned_by
    )


@router.get("/{workspace_id}/threads/{thread_id}/references", response_model=List[ThreadReferenceResponse])
async def list_thread_references(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
) -> List[ThreadReferenceResponse]:
    """
    List all references for a thread
    """
    # Verify thread exists and belongs to workspace
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Thread does not belong to this workspace")

    refs = store.thread_references.get_by_thread(
        workspace_id=workspace_id,
        thread_id=thread_id,
        limit=100
    )

    return [
        ThreadReferenceResponse(
            id=r.id,
            source_type=r.source_type,
            uri=r.uri,
            title=r.title,
            snippet=r.snippet,
            reason=r.reason,
            created_at=r.created_at.isoformat(),
            pinned_by=r.pinned_by or 'user',
        )
        for r in refs
    ]


@router.put("/{workspace_id}/threads/{thread_id}/references/{reference_id}", response_model=ThreadReferenceResponse)
async def update_thread_reference(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    reference_id: str = Path(..., description="Reference ID"),
    request: UpdateReferenceRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
) -> ThreadReferenceResponse:
    """
    Update a thread reference
    """
    # Verify thread exists and belongs to workspace
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Thread does not belong to this workspace")

    # Verify reference exists and belongs to thread
    reference = store.thread_references.get_reference(reference_id)
    if not reference:
        raise HTTPException(status_code=404, detail="Reference not found")

    if reference.thread_id != thread_id:
        raise HTTPException(status_code=403, detail="Reference does not belong to this thread")

    # Update reference
    updates = {}
    if request.title is not None:
        updates['title'] = request.title
    if request.snippet is not None:
        updates['snippet'] = request.snippet
    if request.reason is not None:
        updates['reason'] = request.reason
    updates['updated_at'] = datetime.utcnow()

    if updates:
        store.thread_references.update_reference(reference_id, **updates)
        reference = store.thread_references.get_reference(reference_id)

    return ThreadReferenceResponse(
        id=reference.id,
        source_type=reference.source_type,
        uri=reference.uri,
        title=reference.title,
        snippet=reference.snippet,
        reason=reference.reason,
        created_at=reference.created_at.isoformat(),
        pinned_by=reference.pinned_by or 'user',
    )


@router.delete("/{workspace_id}/threads/{thread_id}/references/{reference_id}")
async def delete_thread_reference(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    reference_id: str = Path(..., description="Reference ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store)
):
    """
    Delete a thread reference
    """
    # Verify thread exists and belongs to workspace
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(status_code=403, detail="Thread does not belong to this workspace")

    # Verify reference exists and belongs to thread
    reference = store.thread_references.get_reference(reference_id)
    if not reference:
        raise HTTPException(status_code=404, detail="Reference not found")

    if reference.thread_id != thread_id:
        raise HTTPException(status_code=403, detail="Reference does not belong to this thread")

    deleted = store.thread_references.delete_reference(reference_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete reference")

    return {"message": "Reference deleted successfully"}
