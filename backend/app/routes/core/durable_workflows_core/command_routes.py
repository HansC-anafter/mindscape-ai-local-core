"""Explicit compare command; replay/fork remain gated with live cutover."""

from fastapi import APIRouter, Request

from .dependencies import execute_review, review_dependencies
from .schemas import CompareRequest

router = APIRouter()


@router.post("/workspaces/{workspace_id}/durable-workflows/compare")
def compare_workflows(
    workspace_id: str, request: Request, payload: CompareRequest
):
    service, connection_provider = review_dependencies(request)
    with connection_provider() as conn:
        return execute_review(
            lambda: service.compare_as_of(
                conn,
                workspace_id=workspace_id,
                left_workflow_id=payload.left.workflow_id,
                left_sequence=payload.left.sequence,
                right_workflow_id=payload.right.workflow_id,
                right_sequence=payload.right.sequence,
            )
        )
