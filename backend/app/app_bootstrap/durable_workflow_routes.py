"""Single composition seam for gated durable workflow review routes."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI

from backend.app.services.workflow.durable_state.review_service import (
    DurableWorkflowReviewService,
)
from backend.app.services.workflow.durable_state.reducers import reduce_v1

logger = logging.getLogger(__name__)


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


def register_runtime_durable_workflow_routes(app: FastAPI) -> bool:
    """Compose bounded reads with the existing core database engine."""

    from backend.app.database.engine import engine_postgres_core

    if engine_postgres_core is None:
        return False
    register_durable_workflow_routes(
        app,
        review_service=DurableWorkflowReviewService(reducers={"reducer.v1": reduce_v1}),
        read_connection=engine_postgres_core.connect,
    )
    return True


def restore_runtime_outcome_adapters(app: FastAPI) -> dict[str, Any]:
    """Restore active neutral adapters through the canonical activation seam."""

    from backend.app.services.capability_runtime_activation import (
        restore_active_outcome_adapters,
    )

    receipt = restore_active_outcome_adapters(app)
    if receipt["failed_count"]:
        logger.error(
            "Durable outcome adapter startup restore failed for %d capabilities",
            receipt["failed_count"],
        )
    return receipt
