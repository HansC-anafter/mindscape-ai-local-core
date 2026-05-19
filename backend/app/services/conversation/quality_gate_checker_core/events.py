"""Event recording for quality gate checks."""

import logging
import uuid

from backend.app.models.mindscape import EventActor, EventType, MindEvent
from backend.app.models.workspace_runtime_profile import QualityGates
from backend.app.services.conversation.quality_gate_checker_core.clock import utc_now
from backend.app.services.conversation.quality_gate_checker_core.models import (
    QualityGateResult,
)

logger = logging.getLogger(__name__)


def record_quality_gate_event(
    *,
    event_store,
    execution_id,
    profile_id,
    workspace_id,
    quality_gates: QualityGates,
    result: QualityGateResult,
):
    """Record a quality gate check event when event recording is configured."""
    if not event_store or not execution_id:
        return

    try:
        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=utc_now(),
            actor=EventActor.SYSTEM,
            channel="runtime_profile",
            profile_id=profile_id or "system",
            workspace_id=workspace_id,
            event_type=EventType.QUALITY_GATE_CHECK,
            payload={
                "execution_id": execution_id,
                "passed": result.passed,
                "failed_gates": result.failed_gates,
                "details": result.details,
                "enabled_gates": {
                    "require_lint": quality_gates.require_lint,
                    "require_tests": quality_gates.require_tests,
                    "require_docs": quality_gates.require_docs,
                    "require_changelist": quality_gates.require_changelist,
                    "require_rollback_plan": quality_gates.require_rollback_plan,
                    "require_citations": quality_gates.require_citations,
                },
            },
        )
        event_store.create(event)
        logger.info(
            "QualityGateChecker: Recorded quality gate check event for "
            "execution_id=%s, passed=%s, failed_gates=%s",
            execution_id,
            result.passed,
            result.failed_gates,
        )
    except Exception as exc:
        logger.warning("Failed to record quality gate check event: %s", exc, exc_info=True)
