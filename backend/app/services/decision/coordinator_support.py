"""Serialization and event helpers for ``UnifiedDecisionCoordinator``."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.app.services.execution_core.clock import utc_now as _utc_now

logger = logging.getLogger(__name__)


def serialize_playbook_contribution(
    playbook_contribution: Any,
) -> Optional[Dict[str, Any]]:
    """Serialize PlaybookPreflightResult with a stable minimum schema."""
    if not playbook_contribution:
        return None

    result = {
        "playbook_code": getattr(playbook_contribution, "playbook_code", None),
        "status": (
            getattr(playbook_contribution.status, "value", None)
            if hasattr(playbook_contribution, "status") and playbook_contribution.status
            else (
                getattr(playbook_contribution, "status", None)
                if isinstance(getattr(playbook_contribution, "status", None), str)
                else None
            )
        ),
        "accepted": getattr(playbook_contribution, "accepted", False),
    }
    if hasattr(playbook_contribution, "missing_inputs"):
        result["missing_inputs"] = playbook_contribution.missing_inputs or []
    if hasattr(playbook_contribution, "clarification_questions"):
        result["clarification_questions"] = (
            playbook_contribution.clarification_questions or []
        )
    if hasattr(playbook_contribution, "rejection_reason"):
        result["rejection_reason"] = playbook_contribution.rejection_reason
    if hasattr(playbook_contribution, "recommended_alternatives"):
        result["recommended_alternatives"] = (
            playbook_contribution.recommended_alternatives or []
        )
    if hasattr(playbook_contribution, "recommended_orchestration"):
        result["recommended_orchestration"] = (
            playbook_contribution.recommended_orchestration
        )
    return result


def serialize_governance_contribution(contribution: Any) -> Optional[Dict[str, Any]]:
    """Serialize arbitrary governance contributions defensively."""
    if not contribution:
        return None
    try:
        return contribution.__dict__ if hasattr(contribution, "__dict__") else None
    except Exception as exc:
        logger.warning("Failed to serialize governance contribution: %s", exc)
        return None


def serialize_conflict(conflict: Any) -> Dict[str, Any]:
    """Serialize conflicts coming from dataclasses or dicts."""
    if hasattr(conflict, "__dict__"):
        return conflict.__dict__
    if isinstance(conflict, dict):
        return conflict
    return {"type": str(type(conflict)), "value": str(conflict)}


def _serialize_intent_contribution(decision_result: Any) -> Dict[str, Any]:
    contribution = decision_result.intent_contribution
    if hasattr(contribution, "to_dict"):
        return contribution.to_dict()
    suggested = getattr(contribution, "suggested_playbook", None)
    return {
        "decision_id": getattr(contribution, "decision_id", decision_result.decision_id),
        "suggested_playbook": {
            "playbook_code": suggested.playbook_code if suggested else None,
            "confidence": suggested.confidence if suggested else 0.0,
            "rationale": suggested.rationale if suggested else "",
            "is_orchestration": suggested.is_orchestration if suggested else False,
            "orchestration_steps": suggested.orchestration_steps if suggested else [],
        }
        if suggested
        else None,
        "alternatives": [
            {
                "playbook_code": alt.playbook_code,
                "confidence": alt.confidence,
                "rationale": alt.rationale,
                "is_orchestration": alt.is_orchestration,
            }
            for alt in getattr(contribution, "alternatives", []) or []
        ],
        "confidence": getattr(contribution, "confidence", 0.0),
        "rationale": getattr(contribution, "rationale", ""),
        "decision_method": getattr(
            contribution, "decision_method", "unified_decision_coordinator"
        ),
        "execution_profile_hint": getattr(contribution, "execution_profile_hint", "fast"),
    }


def build_final_decision_dict(decision_result: Any) -> Dict[str, Any]:
    """Serialize the coordinator output into IntentLog.final_decision."""
    execution_profile = decision_result.execution_profile
    return {
        "selected_playbook_code": decision_result.selected_playbook_code,
        "execution_profile": execution_profile.model_dump()
        if hasattr(execution_profile, "model_dump")
        else execution_profile.__dict__,
        "intent_contribution": _serialize_intent_contribution(decision_result),
        "playbook_contribution": serialize_playbook_contribution(
            decision_result.playbook_contribution
        ),
        "node_governance_contribution": serialize_governance_contribution(
            decision_result.node_governance_contribution
        ),
        "cost_governance_contribution": serialize_governance_contribution(
            decision_result.cost_governance_contribution
        ),
        "memory_contribution": serialize_governance_contribution(
            decision_result.memory_contribution
        ),
        "policy_contribution": serialize_governance_contribution(
            decision_result.policy_contribution
        ),
        "conflicts": [serialize_conflict(c) for c in decision_result.conflicts]
        if decision_result.conflicts
        else [],
        "resolution_strategy": decision_result.resolution_strategy,
        "can_auto_execute": decision_result.can_auto_execute,
        "requires_user_approval": decision_result.requires_user_approval,
    }


def build_governance_decision_payload(
    coordinator: Any,
    decision_result: Any,
) -> Optional[Dict[str, Any]]:
    """Build the governance payload shown on DECISION_REQUIRED cards."""
    if (
        decision_result.cost_governance_contribution
        and not decision_result.cost_governance_contribution.approved
    ):
        cost_gov = decision_result.cost_governance_contribution
        workspace_id = getattr(decision_result, "workspace_id", None) or getattr(
            decision_result.intent_contribution, "workspace_id", None
        )
        quota_limit = 0.0
        current_usage = 0.0
        downgrade_suggestion = None

        if getattr(coordinator, "cost_governance", None):
            try:
                quota_settings = coordinator.cost_governance._get_quota_settings(
                    workspace_id or ""
                )
                quota_limit = quota_settings.get("daily_quota", 0.0)
                current_usage = coordinator.cost_governance._get_today_usage(
                    workspace_id or ""
                )
                if cost_gov.reason and "consider" in cost_gov.reason.lower():
                    downgrade_suggestion = cost_gov.reason
            except Exception:
                pass

        return {
            "type": "cost_exceeded",
            "layer": "cost",
            "approved": False,
            "reason": cost_gov.reason,
            "cost_governance": {
                "estimated_cost": cost_gov.estimated_cost or 0.0,
                "quota_limit": quota_limit,
                "current_usage": current_usage,
                "downgrade_suggestion": downgrade_suggestion,
            },
        }

    if (
        decision_result.node_governance_contribution
        and not decision_result.node_governance_contribution.approved
    ):
        node_gov = decision_result.node_governance_contribution
        reason_lower = (node_gov.reason or "").lower()
        if "blacklist" in reason_lower:
            rejection_reason = "blacklist"
        elif "whitelist" in reason_lower:
            rejection_reason = "whitelist"
        elif "risk" in reason_lower or "label" in reason_lower:
            rejection_reason = "risk_label"
        elif "throttle" in reason_lower or "limit" in reason_lower:
            rejection_reason = "throttle"
        else:
            rejection_reason = "unknown"

        return {
            "type": "node_rejected",
            "layer": "node",
            "approved": False,
            "reason": node_gov.reason,
            "node_governance": {
                "rejection_reason": rejection_reason,
                "affected_playbooks": [decision_result.selected_playbook_code]
                if decision_result.selected_playbook_code
                else [],
                "alternatives": [],
            },
        }

    if (
        decision_result.policy_contribution
        and not decision_result.policy_contribution.approved
    ):
        policy = decision_result.policy_contribution
        reason_lower = (policy.reason or "").lower()
        if "role" in reason_lower:
            violation_type = "role"
        elif "domain" in reason_lower or "data" in reason_lower:
            violation_type = "data_domain"
        elif "pii" in reason_lower:
            violation_type = "pii"
        else:
            violation_type = "unknown"

        return {
            "type": "policy_violation",
            "layer": "policy",
            "approved": False,
            "reason": policy.reason,
            "policy_violation": {
                "violation_type": violation_type,
                "policy_id": None,
                "violation_items": [policy.reason] if policy.reason else [],
                "request_permission_url": None,
            },
        }

    if (
        decision_result.playbook_contribution
        and not decision_result.playbook_contribution.accepted
    ):
        preflight = decision_result.playbook_contribution
        missing_credentials: List[str] = []
        environment_issues: List[str] = []
        if preflight.rejection_reason:
            reason_lower = preflight.rejection_reason.lower()
            if (
                "credential" in reason_lower
                or "api key" in reason_lower
                or "key" in reason_lower
            ):
                missing_credentials = [preflight.rejection_reason]
            elif (
                "environment" in reason_lower
                or "sandbox" in reason_lower
                or "repo" in reason_lower
            ):
                environment_issues = [preflight.rejection_reason]

        return {
            "type": "preflight_failed",
            "layer": "preflight",
            "approved": False,
            "reason": preflight.rejection_reason,
            "preflight_failure": {
                "missing_inputs": preflight.missing_inputs or [],
                "missing_credentials": missing_credentials,
                "environment_issues": environment_issues,
                "recommended_alternatives": preflight.recommended_alternatives or [],
            },
        }

    return None


def emit_decision_required_event(
    coordinator: Any,
    *,
    store: Any,
    decision_result: Any,
    intent_log: Any,
    workspace_id: str,
    project_id: Optional[str],
    user_id: Optional[str],
) -> None:
    """Emit DECISION_REQUIRED event for human-in-the-loop review."""
    from backend.app.models.mindscape import EventActor, EventType, MindEvent

    missing_inputs = list(decision_result.intent_contribution.missing_inputs or [])
    if decision_result.playbook_contribution:
        missing_inputs.extend(decision_result.playbook_contribution.missing_inputs or [])
    clarification_questions = (
        decision_result.playbook_contribution.clarification_questions or []
        if decision_result.playbook_contribution
        else []
    )

    blocked_step_ids: List[str] = []
    if intent_log and getattr(intent_log, "metadata", None):
        execution_plan = intent_log.metadata.get("execution_plan")
        if isinstance(execution_plan, dict):
            tasks = execution_plan.get("tasks", [])
            if isinstance(tasks, list) and (
                missing_inputs
                or clarification_questions
                or decision_result.requires_user_approval
            ):
                blocked_step_ids = [
                    task.get("id") or f"step-{i}"
                    for i, task in enumerate(tasks)
                    if isinstance(task, dict)
                ]

    card_type = "decision"
    if missing_inputs:
        card_type = "input"
    elif clarification_questions or decision_result.conflicts:
        card_type = "review"

    priority = "blocker" if decision_result.requires_user_approval else "normal"
    if decision_result.conflicts:
        priority = "high"

    governance_decision = None
    if (
        decision_result.node_governance_contribution
        and not decision_result.node_governance_contribution.approved
    ) or (
        decision_result.cost_governance_contribution
        and not decision_result.cost_governance_contribution.approved
    ) or (
        decision_result.policy_contribution
        and not decision_result.policy_contribution.approved
    ) or (
        decision_result.playbook_contribution
        and not decision_result.playbook_contribution.accepted
    ):
        governance_decision = build_governance_decision_payload(
            coordinator, decision_result
        )

    try:
        event = MindEvent(
            id=str(uuid.uuid4()),
            timestamp=_utc_now(),
            actor=EventActor.AGENT,
            channel="api",
            profile_id=user_id or "",
            project_id=project_id,
            workspace_id=workspace_id,
            event_type=EventType.DECISION_REQUIRED,
            payload={
                "decision_id": decision_result.decision_id,
                "intent_log_id": intent_log.id,
                "requires_user_approval": decision_result.requires_user_approval,
                "can_auto_execute": decision_result.can_auto_execute,
                "missing_inputs": missing_inputs,
                "clarification_questions": clarification_questions,
                "conflicts": [serialize_conflict(c) for c in decision_result.conflicts]
                if decision_result.conflicts
                else [],
                "blocking_steps": blocked_step_ids,
                "card_type": card_type if not governance_decision else "governance",
                "priority": priority,
                "selected_playbook_code": decision_result.selected_playbook_code,
                "rationale": decision_result.intent_contribution.rationale,
                "governance_decision": governance_decision,
            },
            entity_ids={
                "decision_id": decision_result.decision_id,
                "intent_log_id": intent_log.id,
            },
            metadata={
                "decision_method": decision_result.intent_contribution.decision_method,
                "playbook_code": decision_result.selected_playbook_code,
            },
        )
        store.create_event(event)
        logger.info(
            "Emitted DECISION_REQUIRED event for decision %s",
            decision_result.decision_id,
        )
    except Exception as exc:
        logger.error("Failed to emit DECISION_REQUIRED event: %s", exc, exc_info=True)


def emit_branch_proposed_event(
    *,
    store: Any,
    intent_decision: Any,
    workspace_id: str,
    project_id: Optional[str],
    user_id: Optional[str],
) -> None:
    """Emit BRANCH_PROPOSED event for multiple playbook alternatives."""
    from backend.app.models.mindscape import EventActor, EventType, MindEvent

    alternatives: List[Dict[str, Any]] = []
    if intent_decision.alternatives:
        for i, alt in enumerate(intent_decision.alternatives):
            differences: List[str] = []
            for j, other_alt in enumerate(intent_decision.alternatives):
                if i == j:
                    continue
                if alt.playbook_code != other_alt.playbook_code:
                    differences.append(
                        f"Different playbook: {alt.playbook_code} vs {other_alt.playbook_code}"
                    )
                confidence_diff = abs(alt.confidence - other_alt.confidence)
                if confidence_diff > 0.1:
                    if alt.confidence > other_alt.confidence:
                        differences.append(
                            f"Higher confidence ({alt.confidence:.2f} vs {other_alt.confidence:.2f})"
                        )
                    else:
                        differences.append(
                            f"Lower confidence ({alt.confidence:.2f} vs {other_alt.confidence:.2f})"
                        )
                alt_inputs = set(alt.required_inputs or [])
                other_inputs = set(other_alt.required_inputs or [])
                if alt_inputs != other_inputs:
                    unique_inputs = alt_inputs - other_inputs
                    if unique_inputs:
                        differences.append(
                            f"Requires additional inputs: {', '.join(unique_inputs)}"
                        )
                    missing_inputs = other_inputs - alt_inputs
                    if missing_inputs:
                        differences.append(
                            "Missing inputs compared to others: "
                            + ", ".join(missing_inputs)
                        )

            alternatives.append(
                {
                    "playbook_code": alt.playbook_code,
                    "confidence": alt.confidence,
                    "rationale": alt.rationale,
                    "differences": differences[:3],
                }
            )
    elif intent_decision.suggested_playbook:
        alternatives = [
            {
                "playbook_code": intent_decision.suggested_playbook.playbook_code,
                "confidence": intent_decision.suggested_playbook.confidence,
                "rationale": intent_decision.suggested_playbook.rationale,
                "differences": [],
            }
        ]

    recommended_branch = None
    if intent_decision.suggested_playbook:
        recommended_branch = intent_decision.suggested_playbook.playbook_code
    elif alternatives:
        recommended_branch = max(alternatives, key=lambda item: item["confidence"])[
            "playbook_code"
        ]

    branch_id = f"branch-{intent_decision.decision_id}"

    try:
        if store:
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                actor=EventActor.AGENT,
                channel="api",
                profile_id=user_id or "",
                project_id=project_id,
                workspace_id=workspace_id,
                event_type=EventType.BRANCH_PROPOSED,
                payload={
                    "branch_id": branch_id,
                    "decision_id": intent_decision.decision_id,
                    "alternatives": alternatives,
                    "recommended_branch": recommended_branch,
                    "context": (
                        "Multiple playbook options available. "
                        f"Recommended: {recommended_branch}"
                    ),
                    "rationale": intent_decision.rationale,
                },
                entity_ids={
                    "branch_id": branch_id,
                    "decision_id": intent_decision.decision_id,
                },
                metadata={
                    "decision_method": intent_decision.decision_method,
                },
            )
            store.create_event(event)
            logger.info("Emitted BRANCH_PROPOSED event for branch %s", branch_id)
    except Exception as exc:
        logger.error("Failed to emit BRANCH_PROPOSED event: %s", exc, exc_info=True)


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
