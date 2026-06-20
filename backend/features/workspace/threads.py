"""
Workspace thread routes.

This module keeps the public workspace thread route paths. Implementation
details live in threads_core helpers.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, Body, Depends, Path, Query

from backend.app.models.thread_bundle import ThreadBundle, ThreadReferenceResponse
from backend.app.models.workspace import ConversationThread, Workspace
from backend.app.routes.workspace_dependencies import get_store, get_workspace
from backend.app.services.mindscape_store import MindscapeStore
from backend.features.workspace.threads_core.bundle import build_thread_bundle
from backend.features.workspace.threads_core.crud import (
    create_thread_response,
    delete_thread_response,
    get_thread_response,
    list_threads_response,
    update_thread_response,
)
from backend.features.workspace.threads_core.references import (
    add_reference_response,
    delete_reference_response,
    list_references_response,
    update_reference_response,
)
from backend.features.workspace.threads_core.schemas import (
    AddReferenceRequest,
    CreateThreadRequest,
    UpdateReferenceRequest,
    UpdateThreadRequest,
)

router = APIRouter(prefix="/api/v1/workspaces", tags=["workspaces-threads"])
logger = logging.getLogger(__name__)


@router.post("/{workspace_id}/threads", response_model=ConversationThread)
async def create_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    request: CreateThreadRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> ConversationThread:
    """Create a new conversation thread in a workspace."""
    return create_thread_response(
        workspace_id=workspace_id,
        request=request,
        workspace=workspace,
        store=store,
    )


@router.get("/{workspace_id}/threads", response_model=List[ConversationThread])
async def list_threads(
    workspace_id: str = Path(..., description="Workspace ID"),
    limit: Optional[int] = Query(
        None, ge=1, le=100, description="Maximum number of threads to return"
    ),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> List[ConversationThread]:
    """List conversation threads for a workspace."""
    return list_threads_response(workspace_id=workspace_id, limit=limit, store=store)


@router.get("/{workspace_id}/threads/{thread_id}", response_model=ConversationThread)
async def get_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> ConversationThread:
    """Get a conversation thread by ID."""
    return get_thread_response(
        workspace_id=workspace_id,
        thread_id=thread_id,
        store=store,
    )


@router.put("/{workspace_id}/threads/{thread_id}", response_model=ConversationThread)
async def update_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    request: UpdateThreadRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> ConversationThread:
    """Update a conversation thread."""
    return update_thread_response(
        workspace_id=workspace_id,
        thread_id=thread_id,
        request=request,
        store=store,
    )


@router.delete("/{workspace_id}/threads/{thread_id}")
async def delete_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """Delete a conversation thread."""
    return delete_thread_response(
        workspace_id=workspace_id,
        thread_id=thread_id,
        store=store,
    )


@router.get("/{workspace_id}/threads/{thread_id}/bundle", response_model=ThreadBundle)
def get_thread_bundle(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> ThreadBundle:
    """Get the aggregated thread bundle view."""
    return build_thread_bundle(
        workspace_id=workspace_id,
        thread_id=thread_id,
        store=store,
    )


@router.post(
    "/{workspace_id}/threads/{thread_id}/references",
    response_model=ThreadReferenceResponse,
)
async def add_reference_to_thread(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    request: AddReferenceRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> ThreadReferenceResponse:
    """Add a reference to a thread."""
    return add_reference_response(
        workspace_id=workspace_id,
        thread_id=thread_id,
        request=request,
        store=store,
    )


@router.get(
    "/{workspace_id}/threads/{thread_id}/references",
    response_model=List[ThreadReferenceResponse],
)
async def list_thread_references(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> List[ThreadReferenceResponse]:
    """List all references for a thread."""
    return list_references_response(
        workspace_id=workspace_id,
        thread_id=thread_id,
        store=store,
    )


@router.put(
    "/{workspace_id}/threads/{thread_id}/references/{reference_id}",
    response_model=ThreadReferenceResponse,
)
async def update_thread_reference(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    reference_id: str = Path(..., description="Reference ID"),
    request: UpdateReferenceRequest = Body(...),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
) -> ThreadReferenceResponse:
    """Update a thread reference."""
    return update_reference_response(
        workspace_id=workspace_id,
        thread_id=thread_id,
        reference_id=reference_id,
        request=request,
        store=store,
    )


@router.delete("/{workspace_id}/threads/{thread_id}/references/{reference_id}")
async def delete_thread_reference(
    workspace_id: str = Path(..., description="Workspace ID"),
    thread_id: str = Path(..., description="Thread ID"),
    reference_id: str = Path(..., description="Reference ID"),
    workspace: Workspace = Depends(get_workspace),
    store: MindscapeStore = Depends(get_store),
):
    """Delete a thread reference."""
    return delete_reference_response(
        workspace_id=workspace_id,
        thread_id=thread_id,
        reference_id=reference_id,
        store=store,
    )
