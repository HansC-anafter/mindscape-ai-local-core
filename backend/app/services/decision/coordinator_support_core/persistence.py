"""Persistence helpers for decision coordinator support."""

import logging
import uuid
from typing import Any, Optional

from backend.app.services.decision.coordinator_support_core.events import (
    emit_branch_proposed_event,
    emit_decision_required_event,
)
from backend.app.services.decision.coordinator_support_core.serializers import (
    build_final_decision_dict,
)

logger = logging.getLogger("backend.app.services.decision.coordinator_support")


async def record_governance_decisions(
    *,
    workspace_id: str,
    execution_id: Optional[str],
    node_governance_decision: Optional[Any],
    cost_governance_decision: Optional[Any],
    policy_decision: Optional[Any],
    playbook_preflight_result: Optional[Any],
    playbook_code: Optional[str],
) -> None:
    """Persist governance decisions without failing the coordinator path."""
    try:
        from backend.app.services.governance.decision_recorder import (
            GovernanceDecisionRecorder,
        )

        recorder = GovernanceDecisionRecorder()
        if node_governance_decision:
            await recorder.record_decision(
                workspace_id=workspace_id,
                execution_id=execution_id,
                layer="node",
                approved=node_governance_decision.approved,
                reason=node_governance_decision.reason,
                playbook_code=playbook_code,
            )
        if cost_governance_decision:
            await recorder.record_decision(
                workspace_id=workspace_id,
                execution_id=execution_id,
                layer="cost",
                approved=cost_governance_decision.approved,
                reason=cost_governance_decision.reason,
                playbook_code=playbook_code,
                metadata={
                    "estimated_cost": cost_governance_decision.estimated_cost,
                },
            )
            if (
                cost_governance_decision.approved
                and cost_governance_decision.estimated_cost
            ):
                await recorder.record_cost_usage(
                    workspace_id=workspace_id,
                    execution_id=execution_id,
                    cost=cost_governance_decision.estimated_cost,
                    playbook_code=playbook_code,
                )
        if policy_decision:
            await recorder.record_decision(
                workspace_id=workspace_id,
                execution_id=execution_id,
                layer="policy",
                approved=policy_decision.approved,
                reason=policy_decision.reason,
                playbook_code=playbook_code,
            )
        if playbook_preflight_result:
            await recorder.record_decision(
                workspace_id=workspace_id,
                execution_id=execution_id,
                layer="preflight",
                approved=playbook_preflight_result.accepted,
                reason=playbook_preflight_result.rejection_reason,
                playbook_code=playbook_code,
                metadata={
                    "missing_inputs": playbook_preflight_result.missing_inputs,
                    "clarification_questions": playbook_preflight_result.clarification_questions,
                },
            )
    except Exception as exc:
        logger.warning("Failed to record governance decisions: %s", exc, exc_info=True)


async def store_decision_to_intent_log(
    coordinator: Any,
    *,
    decision_result: Any,
    user_input: str,
    workspace_id: str,
    project_id: Optional[str],
    user_id: Optional[str],
    intent_result: Any,
    playbook_preflight_result: Optional[Any],
    node_governance_decision: Optional[Any],
    cost_governance_decision: Optional[Any],
    memory_recommendation: Optional[Any],
    policy_decision: Optional[Any],
) -> None:
    """Store UnifiedDecisionResult to IntentLog and emit side events."""
    from backend.app.models.mindscape import IntentLog
    from backend.app.services.mindscape_store import MindscapeStore

    store = MindscapeStore()
    log_id = decision_result.decision_id
    max_retries = 3
    retry_count = 0
    while retry_count < max_retries:
        existing_log = store.get_intent_log(log_id)
        if existing_log:
            logger.warning(
                "IntentLog with decision_id %s already exists, generating new UUID (retry %s/%s)",
                log_id,
                retry_count + 1,
                max_retries,
            )
            log_id = str(uuid.uuid4())
            decision_result.decision_id = log_id
            retry_count += 1
        else:
            break

    if retry_count >= max_retries:
        logger.error(
            "Failed to generate unique IntentLog.id after %s retries, using final attempt: %s",
            max_retries,
            log_id,
        )

    intent_log = IntentLog(
        id=log_id,
        timestamp=decision_result.timestamp,
        raw_input=user_input,
        channel="api",
        profile_id=user_id or "",
        project_id=project_id,
        workspace_id=workspace_id,
        pipeline_steps={
            "intent_analysis": getattr(intent_result, "pipeline_steps", {})
            if hasattr(intent_result, "pipeline_steps")
            else {},
            "playbook_preflight": playbook_preflight_result.__dict__
            if playbook_preflight_result
            else None,
            "node_governance": node_governance_decision.__dict__
            if node_governance_decision
            else None,
            "cost_governance": cost_governance_decision.__dict__
            if cost_governance_decision
            else None,
            "policy": policy_decision.__dict__ if policy_decision else None,
        },
        final_decision=build_final_decision_dict(decision_result),
        user_override=None,
        metadata={
            "decision_id": decision_result.decision_id,
            "decision_method": "unified_decision_coordinator",
            "version": "1.0",
        },
    )

    try:
        store.create_intent_log(intent_log)
        logger.info(
            "Successfully stored UnifiedDecisionResult to IntentLog: %s",
            log_id,
        )
        has_alternatives = bool(
            decision_result.intent_contribution.alternatives
            and len(decision_result.intent_contribution.alternatives) > 0
        )
        if has_alternatives:
            emit_branch_proposed_event(
                store=store,
                intent_decision=decision_result.intent_contribution,
                workspace_id=workspace_id,
                project_id=project_id,
                user_id=user_id,
            )
        if decision_result.requires_user_approval:
            emit_decision_required_event(
                coordinator,
                store=store,
                decision_result=decision_result,
                intent_log=intent_log,
                workspace_id=workspace_id,
                project_id=project_id,
                user_id=user_id,
            )
    except Exception as exc:
        logger.error(
            "Failed to store UnifiedDecisionResult to IntentLog: %s",
            exc,
            exc_info=True,
        )
        raise
