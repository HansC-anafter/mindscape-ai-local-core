"""Single composition seam for gated durable workflow review routes."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from backend.app.services.workflow.durable_state.review_service import (
    DurableWorkflowReviewService,
)


def register_durable_workflow_routes(
    app: FastAPI,
    *,
    review_service: DurableWorkflowReviewService,
    read_connection: Callable[[], Any],
) -> None:
    """Publish routes only when the gated caller supplies both dependencies."""

    from backend.app.routes.core.durable_workflows import router

    app.state.durable_workflow_review_service = review_service
    app.state.durable_workflow_read_connection = read_connection
    app.include_router(router)
