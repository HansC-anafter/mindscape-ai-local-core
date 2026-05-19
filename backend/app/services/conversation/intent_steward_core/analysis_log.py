"""Intent steward analysis log writer."""

import logging
import uuid

from backend.app.models.mindscape import IntentLayoutPlan, IntentLog
from backend.app.services.conversation.intent_steward_core.runtime import utc_now

logger = logging.getLogger(__name__)


async def write_analysis_log(
    service,
    layout_plan: IntentLayoutPlan,
    workspace_id: str,
    profile_id: str,
    turn_id: str,
) -> None:
    try:
        intent_log = IntentLog(
            id=str(uuid.uuid4()),
            timestamp=utc_now(),
            raw_input=f"IntentSteward analysis for turn {turn_id}",
            channel="intent_steward",
            profile_id=profile_id,
            workspace_id=workspace_id,
            pipeline_steps={
                "steward_version": (
                    "v2_phase2"
                    if layout_plan.metadata.get("executed")
                    else "v2_phase1"
                ),
                "mode": layout_plan.metadata.get("mode", "observation"),
            },
            final_decision={
                "layout_plan": layout_plan.model_dump(),
                "planned_operations": len(layout_plan.long_term_intents),
                "ephemeral_tasks": len(layout_plan.ephemeral_tasks),
                "signal_mappings": len(layout_plan.signal_mapping),
            },
            metadata={
                "turn_id": turn_id,
                "steward_phase": (
                    "phase2_execution"
                    if layout_plan.metadata.get("executed")
                    else "phase1_observation"
                ),
                "executed": layout_plan.metadata.get("executed", False),
                "executed_operations": layout_plan.metadata.get(
                    "executed_operations", []
                ),
            },
        )
        service.store.create_intent_log(intent_log)
        logger.info(
            f"INTENT_STEWARD_LOG: turn_id={turn_id}, workspace_id={workspace_id}, "
            f"profile_id={profile_id}, planned_operations={len(layout_plan.long_term_intents)}, "
            f"ephemeral_tasks={len(layout_plan.ephemeral_tasks)}, "
            f"timestamp={utc_now().isoformat()}"
        )
    except Exception as exc:
        logger.error(
            f"Failed to write IntentSteward analysis log: {exc}", exc_info=True
        )
