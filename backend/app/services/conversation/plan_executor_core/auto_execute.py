"""Plan executor auto-execute decisions."""

import logging
from typing import Any, Dict, Optional

from backend.app.models.workspace import SideEffectLevel

logger = logging.getLogger(__name__)


def determine_auto_execute(
    *,
    task_plan,
    side_effect_level: SideEffectLevel,
    execution_mode: str,
    execution_priority: str,
    auto_exec_config: Optional[Dict[str, Any]],
) -> bool:
    should_auto_execute = task_plan.auto_execute
    llm_confidence = (
        task_plan.params.get("llm_analysis", {}).get("confidence", 0.0)
        if task_plan.params
        else 0.0
    )

    if (
        execution_mode in ("execution", "hybrid")
        and side_effect_level == SideEffectLevel.READONLY
    ):
        from backend.app.shared.execution_thresholds import (
            should_auto_execute_readonly,
        )

        should_auto_execute = should_auto_execute_readonly(
            execution_priority, llm_confidence
        )
        logger.info(
            f"PlanExecutor: READONLY task {task_plan.pack_id} auto-execute={should_auto_execute} "
            f"(execution_mode={execution_mode}, priority={execution_priority}, confidence={llm_confidence:.2f})"
        )
    elif auto_exec_config and task_plan.pack_id in auto_exec_config:
        from backend.app.shared.execution_thresholds import get_threshold

        playbook_config = auto_exec_config[task_plan.pack_id]
        default_threshold = get_threshold(execution_priority)
        confidence_threshold = playbook_config.get(
            "confidence_threshold", default_threshold
        )
        auto_execute_enabled = playbook_config.get("auto_execute", False)

        if auto_execute_enabled and llm_confidence >= confidence_threshold:
            should_auto_execute = True
            logger.info(
                f"PlanExecutor: Playbook {task_plan.pack_id} meets auto-exec threshold "
                f"(confidence={llm_confidence:.2f} >= {confidence_threshold:.2f})"
            )
        else:
            should_auto_execute = False
            logger.info(
                f"PlanExecutor: Playbook {task_plan.pack_id} does not meet auto-exec threshold "
                f"(confidence={llm_confidence:.2f} < {confidence_threshold:.2f})"
            )

    return should_auto_execute
