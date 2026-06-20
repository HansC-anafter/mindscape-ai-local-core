"""Thread reference CRUD helpers."""

import uuid
from datetime import datetime

from backend.app.models.thread_bundle import ThreadReferenceResponse
from backend.app.models.workspace import ThreadReference
from backend.app.services.mindscape_store import MindscapeStore
from backend.features.workspace.threads_core.schemas import (
    AddReferenceRequest,
    UpdateReferenceRequest,
)
from backend.features.workspace.threads_core.validation import (
    get_reference_or_404,
    get_thread_or_404,
)


def _reference_response(reference) -> ThreadReferenceResponse:
    return ThreadReferenceResponse(
        id=reference.id,
        source_type=reference.source_type,
        uri=reference.uri,
        title=reference.title,
        snippet=reference.snippet,
        reason=reference.reason,
        created_at=reference.created_at.isoformat(),
        pinned_by=reference.pinned_by or "user",
    )


def add_reference_response(
    *,
    workspace_id: str,
    thread_id: str,
    request: AddReferenceRequest,
    store: MindscapeStore,
) -> ThreadReferenceResponse:
    get_thread_or_404(store, workspace_id=workspace_id, thread_id=thread_id)
    reference = ThreadReference(
        id=str(uuid.uuid4()),
        workspace_id=workspace_id,
        thread_id=thread_id,
        source_type=request.source_type,
        uri=request.uri,
        title=request.title,
        snippet=request.snippet,
        reason=request.reason,
        pinned_by="user",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    created_reference = store.thread_references.create_reference(reference)
    return _reference_response(created_reference)


def list_references_response(
    *,
    workspace_id: str,
    thread_id: str,
    store: MindscapeStore,
) -> list[ThreadReferenceResponse]:
    get_thread_or_404(store, workspace_id=workspace_id, thread_id=thread_id)
    refs = store.thread_references.get_by_thread(
        workspace_id=workspace_id, thread_id=thread_id, limit=100
    )
    return [_reference_response(reference) for reference in refs]


def update_reference_response(
    *,
    workspace_id: str,
    thread_id: str,
    reference_id: str,
    request: UpdateReferenceRequest,
    store: MindscapeStore,
) -> ThreadReferenceResponse:
    get_thread_or_404(store, workspace_id=workspace_id, thread_id=thread_id)
    reference = get_reference_or_404(
        store,
        thread_id=thread_id,
        reference_id=reference_id,
    )
    updates = {}
    if request.title is not None:
        updates["title"] = request.title
    if request.snippet is not None:
        updates["snippet"] = request.snippet
    if request.reason is not None:
        updates["reason"] = request.reason
    updates["updated_at"] = datetime.utcnow()

    if updates:
        store.thread_references.update_reference(reference_id, **updates)
        reference = store.thread_references.get_reference(reference_id)

    return _reference_response(reference)


def delete_reference_response(
    *,
    workspace_id: str,
    thread_id: str,
    reference_id: str,
    store: MindscapeStore,
):
    get_thread_or_404(store, workspace_id=workspace_id, thread_id=thread_id)
    get_reference_or_404(
        store,
        thread_id=thread_id,
        reference_id=reference_id,
    )
    deleted = store.thread_references.delete_reference(reference_id)
    if not deleted:
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Failed to delete reference")
    return {"message": "Reference deleted successfully"}
