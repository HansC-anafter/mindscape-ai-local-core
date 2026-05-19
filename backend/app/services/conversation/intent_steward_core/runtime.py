"""Intent steward turn orchestration."""

import logging
from datetime import datetime, timezone
from typing import Optional

from backend.app.models.mindscape import IntentLayoutPlan

logger = logging.getLogger(__name__)


def utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


async def analyze_turn(
    service,
    workspace_id: str,
    profile_id: str,
    turn_id: str,
    conversation_id: Optional[str] = None,
) -> IntentLayoutPlan:
    try:
        logger.info(
            f"IntentSteward: Starting analysis for turn {turn_id}, "
            f"workspace={workspace_id}, profile={profile_id}"
        )

        service._current_workspace_id = workspace_id

        steward_input = await service._collect_input_data(
            workspace_id=workspace_id, profile_id=profile_id, turn_id=turn_id
        )

        filtered_signals = await service.prefilter_signals(steward_input.recent_signals)
        layout_plan = await service.steward_analyze(
            filtered_signals=filtered_signals,
            context=steward_input,
        )

        layout_plan.metadata.update(
            {
                "turn_id": turn_id,
                "workspace_id": workspace_id,
                "profile_id": profile_id,
                "conversation_id": conversation_id,
                "steward_version": "v2_phase1",
                "timestamp": utc_now().isoformat(),
                "mode": "observation",
            }
        )

        auto_layout_enabled = await service._check_auto_layout_flag(
            profile_id, workspace_id
        )
        if auto_layout_enabled:
            await service._execute_layout_plan(
                layout_plan, workspace_id, profile_id, turn_id
            )
            layout_plan.metadata["executed"] = True
            layout_plan.metadata["mode"] = "execution"
        else:
            layout_plan.metadata["executed"] = False
            layout_plan.metadata["mode"] = "observation"

        await service._write_analysis_log(layout_plan, workspace_id, profile_id, turn_id)

        logger.info(
            f"IntentSteward: Analysis complete for turn {turn_id}, "
            f"planned {len(layout_plan.long_term_intents)} intent operations, "
            f"{len(layout_plan.ephemeral_tasks)} ephemeral tasks, "
            f"executed={auto_layout_enabled}"
        )
        return layout_plan
    except Exception as exc:
        logger.error(
            f"IntentSteward: Failed to analyze turn {turn_id}: {exc}",
            exc_info=True,
        )
        return IntentLayoutPlan(
            metadata={
                "turn_id": turn_id,
                "workspace_id": workspace_id,
                "profile_id": profile_id,
                "error": str(exc),
                "timestamp": utc_now().isoformat(),
            }
        )
