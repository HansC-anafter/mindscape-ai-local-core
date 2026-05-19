"""Execution-plan orchestration helpers for PlanBuilder."""

from __future__ import annotations

import logging
import uuid
from typing import Any, Dict, List, Optional

from ....models.workspace import ExecutionPlan
from .llm_generation import generate_llm_plan
from .llm_trace import utc_now
from .rule_based import (
    build_rule_based_task_plans,
    collect_effective_playbook_codes,
    resolve_available_packs,
)
from .runtime import finalize_execution_plan

logger = logging.getLogger(__name__)


async def generate_execution_plan(
    builder: Any,
    *,
    message: str,
    files: List[str],
    workspace_id: str,
    profile_id: str,
    message_id: Optional[str] = None,
    use_llm: bool = True,
    project_id: Optional[str] = None,
    project_assignment_decision: Optional[Dict[str, Any]] = None,
    effective_playbooks: Optional[List[Dict[str, Any]]] = None,
    available_playbooks: Optional[List[Dict[str, Any]]] = None,
    routing_decision: Optional[Any] = None,
    thread_id: Optional[str] = None,
) -> ExecutionPlan:
    """Generate an execution plan using LLM-first, rule-based fallback."""
    del routing_decision

    playbooks_to_use = (
        effective_playbooks if effective_playbooks is not None else available_playbooks
    )

    if effective_playbooks is None and available_playbooks is not None:
        logger.warning(
            "PlanBuilder.generate_execution_plan: effective_playbooks not provided, "
            "using deprecated available_playbooks. This will be deprecated in future versions."
        )

    task_plans = []
    available_packs = resolve_available_packs(builder.is_pack_available)

    if playbooks_to_use:
        effective_playbook_codes = collect_effective_playbook_codes(playbooks_to_use)
        logger.info(
            "PlanBuilder: Using %s effective playbooks: %s...",
            len(effective_playbook_codes),
            list(effective_playbook_codes)[:5],
        )

    if use_llm:
        try:
            llm_plans = await generate_llm_plan(
                builder,
                message=message,
                files=files,
                workspace_id=workspace_id,
                profile_id=profile_id,
                available_packs=available_packs,
                project_id=project_id,
                project_assignment_decision=project_assignment_decision,
                thread_id=thread_id,
            )
            if llm_plans:
                task_plans.extend(llm_plans)
                logger.info(
                    "PlanBuilder: LLM generated %s task plans",
                    len(llm_plans),
                )
                execution_plan = ExecutionPlan(
                    message_id=message_id or str(uuid.uuid4()),
                    workspace_id=workspace_id,
                    tasks=task_plans,
                    created_at=utc_now(),
                    project_id=project_id,
                    project_assignment_decision=project_assignment_decision,
                )
                return await finalize_execution_plan(
                    builder,
                    execution_plan=execution_plan,
                    project_id=project_id,
                    message_id=message_id or execution_plan.message_id,
                    project_assignment_decision=project_assignment_decision,
                    playbooks_to_use=playbooks_to_use,
                )

            logger.info(
                "PlanBuilder: LLM planning returned no plans, falling back to rule-based"
            )
        except Exception as exc:
            logger.warning(
                "PlanBuilder: LLM planning failed: %s, falling back to rule-based",
                exc,
            )

    task_plans.extend(
        build_rule_based_task_plans(
            builder=builder,
            message=message,
            files=files,
        )
    )

    execution_plan = ExecutionPlan(
        message_id=message_id or str(uuid.uuid4()),
        workspace_id=workspace_id,
        tasks=task_plans,
        created_at=utc_now(),
        project_id=project_id,
        project_assignment_decision=project_assignment_decision,
    )

    return await finalize_execution_plan(
        builder,
        execution_plan=execution_plan,
        project_id=project_id,
        message_id=message_id or execution_plan.message_id,
        project_assignment_decision=project_assignment_decision,
        playbooks_to_use=playbooks_to_use,
    )
