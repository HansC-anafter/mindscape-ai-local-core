"""MindEvent emission helpers for decision coordinator support."""

import logging
import uuid
from typing import Any, Dict, List, Optional

from backend.app.services.decision.coordinator_support_core.governance_payload import (
    build_governance_decision_payload,
)
from backend.app.services.decision.coordinator_support_core.serializers import (
    serialize_conflict,
)
from backend.app.services.execution_core.clock import utc_now as _utc_now

logger = logging.getLogger("backend.app.services.decision.coordinator_support")


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
            entity_ids=[decision_result.decision_id, intent_log.id],
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
                entity_ids=[branch_id, intent_decision.decision_id],
                metadata={
                    "decision_method": intent_decision.decision_method,
                },
            )
            store.create_event(event)
            logger.info("Emitted BRANCH_PROPOSED event for branch %s", branch_id)
    except Exception as exc:
        logger.error("Failed to emit BRANCH_PROPOSED event: %s", exc, exc_info=True)
