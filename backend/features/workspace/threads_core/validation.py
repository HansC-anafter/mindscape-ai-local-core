"""Validation helpers for workspace thread routes."""

from fastapi import HTTPException


def get_thread_or_404(store, *, workspace_id: str, thread_id: str):
    thread = store.conversation_threads.get_thread(thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    if thread.workspace_id != workspace_id:
        raise HTTPException(
            status_code=403, detail="Thread does not belong to this workspace"
        )

    return thread


def get_reference_or_404(store, *, thread_id: str, reference_id: str):
    reference = store.thread_references.get_reference(reference_id)
    if not reference:
        raise HTTPException(status_code=404, detail="Reference not found")

    if reference.thread_id != thread_id:
        raise HTTPException(
            status_code=403, detail="Reference does not belong to this thread"
        )

    return reference
