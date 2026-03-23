"""Rule-based fallback planning helpers for PlanBuilder."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Sequence, Set

from ....models.workspace import ExecutionPlan, SideEffectLevel, TaskPlan
from ...capability_registry import get_registry

logger = logging.getLogger(__name__)

PLANNING_KEYWORDS = [
    "task",
    "plan",
    "todo",
    "planning",
    "schedule",
    "待辦",
    "任務",
    "計劃",
]
SUMMARY_KEYWORDS = ["summary", "summarize", "summary of", "摘要", "總結"]
DRAFT_KEYWORDS = ["draft", "草稿", "寫", "generate", "create"]


def resolve_available_packs(is_pack_available_func) -> List[str]:
    """Return the subset of registered packs that are currently available."""
    registry = get_registry()
    return [
        pack_id
        for pack_id in registry.capabilities.keys()
        if is_pack_available_func(pack_id)
    ]


def collect_effective_playbook_codes(
    playbooks_to_use: Optional[List[Dict[str, Any]]],
) -> Set[str]:
    """Collect the effective playbook codes for logging/telemetry."""
    if not playbooks_to_use:
        return set()
    return {
        playbook.get("playbook_code")
        for playbook in playbooks_to_use
        if playbook.get("playbook_code")
    }


def attach_effective_playbooks(
    execution_plan: ExecutionPlan,
    playbooks_to_use: Optional[Sequence[Dict[str, Any]]],
) -> None:
    """Attach effective playbook metadata in the legacy-compatible location."""
    if playbooks_to_use is None:
        return

    if not hasattr(execution_plan, "_metadata"):
        execution_plan._metadata = {}
    execution_plan._metadata["effective_playbooks"] = list(playbooks_to_use)
    execution_plan._metadata["effective_playbooks_count"] = len(playbooks_to_use)


def _append_task_for_pack(
    *,
    builder: Any,
    task_plans: List[TaskPlan],
    pack_id: str,
    task_type: str,
    params: Dict[str, Any],
    readonly_auto_execute: bool,
) -> None:
    if not builder.is_pack_available(pack_id):
        logger.warning("Pack %s is not available, skipping", pack_id)
        return
    if not builder.check_pack_tools_configured(pack_id):
        logger.warning("Pack %s tools are not configured, skipping", pack_id)
        return

    level = builder.determine_side_effect_level(pack_id)
    auto_execute = readonly_auto_execute and level == SideEffectLevel.READONLY
    requires_cta = not auto_execute

    task_plans.append(
        TaskPlan(
            pack_id=pack_id,
            task_type=task_type,
            params=params,
            side_effect_level=level.value,
            auto_execute=auto_execute,
            requires_cta=requires_cta,
        )
    )


def build_rule_based_task_plans(
    *,
    builder: Any,
    message: str,
    files: List[str],
) -> List[TaskPlan]:
    """Build fallback task plans when LLM planning returns nothing."""
    task_plans: List[TaskPlan] = []
    message_lower = message.lower()

    if files:
        _append_task_for_pack(
            builder=builder,
            task_plans=task_plans,
            pack_id="semantic_seeds",
            task_type="extract_intents",
            params={"files": files},
            readonly_auto_execute=True,
        )

    if any(keyword in message_lower for keyword in PLANNING_KEYWORDS):
        _append_task_for_pack(
            builder=builder,
            task_plans=task_plans,
            pack_id="daily_planning",
            task_type="generate_tasks",
            params={"source": "message"},
            readonly_auto_execute=True,
        )

    if any(keyword in message_lower for keyword in SUMMARY_KEYWORDS + DRAFT_KEYWORDS):
        output_type = (
            "summary"
            if any(keyword in message_lower for keyword in SUMMARY_KEYWORDS)
            else "draft"
        )
        _append_task_for_pack(
            builder=builder,
            task_plans=task_plans,
            pack_id="content_drafting",
            task_type=f"generate_{output_type}",
            params={"source": "message", "output_type": output_type},
            readonly_auto_execute=False,
        )

    return task_plans
