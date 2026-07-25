"""Bounded read routes; no SQL, pack dispatch, or owned connection."""

from fastapi import APIRouter, Query, Request

from .dependencies import execute_review, review_dependencies

router = APIRouter()


@router.get("/workspaces/{workspace_id}/executions/{execution_id}/durability")
def execution_durability(workspace_id: str, execution_id: str, request: Request):
    service, connection_provider = review_dependencies(request)
    with connection_provider() as conn:
        return execute_review(
            lambda: service.execution_summary(
                conn, workspace_id=workspace_id, execution_id=execution_id
            )
        )


@router.get("/workspaces/{workspace_id}/durable-workflows/{workflow_id}/events")
def workflow_events(
    workspace_id: str,
    workflow_id: str,
    request: Request,
    cursor: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=50),
):
    service, connection_provider = review_dependencies(request)
    with connection_provider() as conn:
        return execute_review(
            lambda: {
                "events": service.events_after(
                    conn,
                    workspace_id=workspace_id,
                    workflow_id=workflow_id,
                    cursor=cursor,
                    limit=limit,
                )
            }
        )


@router.get(
    "/workspaces/{workspace_id}/durable-workflows/{workflow_id}/checkpoints"
)
def workflow_checkpoints(
    workspace_id: str,
    workflow_id: str,
    request: Request,
    cursor: int = Query(-1, ge=-1),
    limit: int = Query(50, ge=1, le=50),
):
    service, connection_provider = review_dependencies(request)
    with connection_provider() as conn:
        return execute_review(
            lambda: {
                "checkpoints": service.checkpoints_after(
                    conn,
                    workspace_id=workspace_id,
                    workflow_id=workflow_id,
                    cursor=cursor,
                    limit=limit,
                )
            }
        )


@router.get("/workspaces/{workspace_id}/durable-workflows/{workflow_id}/as-of")
def workflow_as_of(
    workspace_id: str,
    workflow_id: str,
    request: Request,
    sequence: int = Query(..., ge=0, le=50),
):
    service, connection_provider = review_dependencies(request)
    with connection_provider() as conn:
        return execute_review(
            lambda: service.as_of(
                conn,
                workspace_id=workspace_id,
                workflow_id=workflow_id,
                target_sequence=sequence,
            )
        )
