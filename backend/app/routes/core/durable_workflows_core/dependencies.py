"""App-state dependencies for source-only durable review routes."""

from fastapi import HTTPException, Request

def review_dependencies(request: Request):
    service = getattr(request.app.state, "durable_workflow_review_service", None)
    connection_provider = getattr(
        request.app.state, "durable_workflow_read_connection", None
    )
    if service is None or connection_provider is None:
        raise HTTPException(
            status_code=503,
            detail="durable workflow review source is not runtime-enabled",
        )
    return service, connection_provider


def execute_review(operation):
    try:
        return operation()
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc.args[0])) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
