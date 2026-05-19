"""StageResult helpers for WorkflowTracker."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, Optional

from backend.app.services.conversation.workflow_tracker_core.clock import utc_now
from backend.app.services.stores.stage_results_store import StageResult

logger = logging.getLogger(__name__)


def create_stage_result(
    *,
    tracker: Any,
    execution_id: str,
    step_id: str,
    stage_name: str,
    result_type: str,
    content: Dict[str, Any],
    preview: Optional[str] = None,
    requires_review: bool = False,
    artifact_id: Optional[str] = None,
) -> StageResult:
    stage_result_id = str(uuid.uuid4())

    stage_result = StageResult(
        id=stage_result_id,
        execution_id=execution_id,
        step_id=step_id,
        stage_name=stage_name,
        result_type=result_type,
        content=content,
        preview=preview,
        requires_review=requires_review,
        review_status="pending" if requires_review else None,
        artifact_id=artifact_id,
        created_at=utc_now(),
    )

    try:
        tracker.stage_results_store.create_stage_result(stage_result)
        logger.debug("Created StageResult: %s for stage %s", stage_result_id, stage_name)
    except Exception as exc:
        logger.warning("Failed to create StageResult: %s", exc)

    return stage_result
