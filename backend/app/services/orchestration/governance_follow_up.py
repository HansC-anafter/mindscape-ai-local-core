"""Acceptance and remediation helpers for ``GovernanceEngine``."""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def resolve_governance_payload(engine: Any, execution_id: str) -> Optional[Dict[str, Any]]:
    """Resolve governance payload from top-level, nested metadata, or inputs."""
    from backend.app.models.execution_metadata import extract_governance_payload

    task = engine.tasks_store.get_task_by_execution_id(execution_id)
    if not task:
        return None

    context = getattr(task, "execution_context", None) or {}
    top_level = extract_governance_payload({"governance": context.get("governance")})
    if top_level:
        return top_level

    execution_metadata = context.get("execution_metadata")
    nested = extract_governance_payload(
        execution_metadata if isinstance(execution_metadata, dict) else None
    )
    if nested:
        return nested

    inputs = context.get("inputs")
    return extract_governance_payload(inputs if isinstance(inputs, dict) else None)


def resolve_acceptance_tests(engine: Any, execution_id: str) -> Optional[List[str]]:
    """Resolve acceptance tests from the task's GovernanceContext."""
    try:
        governance = resolve_governance_payload(engine, execution_id)
        if isinstance(governance, dict):
            return governance.get("acceptance_tests")
    except Exception as exc:
        logger.debug(
            "GovernanceEngine: acceptance_tests resolve failed for exec=%s: %s",
            execution_id,
            exc,
        )
    return None


def calculate_acceptance_pass_rate(eval_summary: Dict[str, Any]) -> float:
    """Compute pass rate across explicit acceptance checks only."""
    checks = eval_summary.get("checks") if isinstance(eval_summary, dict) else None
    if not isinstance(checks, list):
        return 1.0

    acceptance_checks = [
        check
        for check in checks
        if isinstance(check, dict)
        and isinstance(check.get("test"), str)
        and check["test"].startswith("acceptance:")
    ]
    if not acceptance_checks:
        return 1.0

    passed = sum(1 for check in acceptance_checks if check.get("passed"))
    return round(passed / len(acceptance_checks), 3)


def sync_correctness_signals(
    engine: Any,
    *,
    execution_id: str,
    artifact_id: Optional[str],
    playbook_code: Optional[str],
    eval_summary: Dict[str, Any],
    remediation: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Mirror correctness summary into meeting-session metadata."""
    task = None
    task_context: Dict[str, Any] = {}
    meeting_session_id = None
    remediation_round = 0

    try:
        task = engine.tasks_store.get_task_by_execution_id(execution_id)
        if task:
            task_context = getattr(task, "execution_context", None) or {}
            remediation_round = int(task_context.get("remediation_round", 0) or 0)
            meeting_session_id = (
                getattr(task, "meeting_session_id", None)
                or task_context.get("meeting_session_id")
            )
            if not meeting_session_id:
                inputs = task_context.get("inputs")
                if isinstance(inputs, dict):
                    meeting_session_id = inputs.get("meeting_session_id")
    except Exception as exc:
        logger.debug(
            "GovernanceEngine: correctness signal task resolve failed for exec=%s: %s",
            execution_id,
            exc,
        )

    if isinstance(remediation, dict):
        try:
            remediation_round = int(
                remediation.get("remediation_round", remediation_round) or 0
            )
        except Exception:
            pass

    acceptance_pass_rate = calculate_acceptance_pass_rate(eval_summary)
    eval_summary["acceptance_pass_rate"] = acceptance_pass_rate
    eval_summary["remediation_round"] = remediation_round
    if isinstance(remediation, dict) and "should_follow_up" in remediation:
        eval_summary["should_follow_up"] = bool(remediation.get("should_follow_up"))

    summary = {
        "passed": bool(eval_summary.get("passed", True)),
        "quality_score": float(
            eval_summary["quality_score"]
            if "quality_score" in eval_summary
            and eval_summary.get("quality_score") is not None
            else 1.0
        ),
        "acceptance_pass_rate": acceptance_pass_rate,
        "remediation_round": remediation_round,
        "execution_id": execution_id,
        "artifact_id": artifact_id,
        "playbook_code": playbook_code,
        "should_follow_up": bool(
            remediation.get("should_follow_up")
            if isinstance(remediation, dict)
            else False
        ),
    }

    if not meeting_session_id:
        return summary

    try:
        session = engine.meeting_session_store.get_by_id(meeting_session_id)
        if session:
            if session.metadata is None:
                session.metadata = {}
            session.metadata["correctness_signals"] = dict(summary)
            engine.meeting_session_store.update(session)
            logger.info(
                "GovernanceEngine: correctness signals synced session=%s exec=%s score=%.2f round=%d",
                meeting_session_id,
                execution_id,
                summary["quality_score"],
                summary["remediation_round"],
            )
    except Exception as exc:
        logger.warning(
            "GovernanceEngine: correctness signal sync failed (non-fatal): %s",
            exc,
        )

    return summary


def backfill_eval_summary(
    engine: Any,
    *,
    artifact_id: str,
    eval_summary: Dict[str, Any],
) -> None:
    """Persist eval_summary into artifact.metadata.provenance."""
    try:
        def _merge_eval_summary(metadata: Dict[str, Any]) -> None:
            provenance = (
                metadata.get("provenance")
                if isinstance(metadata.get("provenance"), dict)
                else {}
            )
            provenance["eval_summary"] = eval_summary
            metadata["provenance"] = provenance

        updated = engine._update_artifact_metadata(
            artifact_id=artifact_id,
            updater=_merge_eval_summary,
        )
        if updated:
            logger.info(
                "GovernanceEngine: eval_summary backfilled artifact=%s passed=%s score=%.2f",
                artifact_id,
                eval_summary.get("passed"),
                eval_summary.get("quality_score", 0),
            )
    except Exception as exc:
        logger.warning(
            "GovernanceEngine: eval_summary backfill failed (non-fatal): %s",
            exc,
        )


def create_follow_up_task(
    engine: Any,
    *,
    workspace_id: str,
    playbook_code: Optional[str],
    follow_up_context: Dict[str, Any],
) -> None:
    """Create a follow-up task carrying remediation context."""
    import uuid

    try:
        idempotency_key = follow_up_context.get("idempotency_key", "")
        task_ir_id = follow_up_context.get("task_ir_id") or ""
        if idempotency_key:
            from backend.app.services.stores.handoff_registry_store import (
                HandoffRegistryStore,
            )

            registry = HandoffRegistryStore()
            ok = registry.register_attempt(
                idempotency_key=idempotency_key,
                task_ir_id=task_ir_id,
                phase_id=f"remediation-{follow_up_context.get('remediation_round', 0)}",
            )
            if not ok:
                logger.info(
                    "GovernanceEngine: follow-up already created for key=%s",
                    idempotency_key,
                )
                return

        from backend.app.models.workspace import Task, TaskStatus

        remediation_round = follow_up_context.get("remediation_round", 1)
        original_execution_id = follow_up_context.get("original_execution_id", "")
        message_id = (
            follow_up_context.get("original_message_id")
            or f"remediation-{original_execution_id}-r{remediation_round}"
        )
        follow_up_governance = {
            "acceptance_tests": follow_up_context.get("acceptance_tests"),
        }
        follow_up_governance = {
            key: value
            for key, value in follow_up_governance.items()
            if value is not None
        }
        follow_up_execution_context = {
            "remediation_round": remediation_round,
            "original_execution_id": original_execution_id,
            "original_artifact_id": follow_up_context.get("original_artifact_id"),
            "eval_reasons": follow_up_context.get("eval_reasons", []),
            "eval_quality_score": follow_up_context.get("eval_quality_score"),
            "task_ir_id": task_ir_id,
            "playbook_code": playbook_code,
        }
        if follow_up_governance:
            follow_up_execution_context["governance"] = follow_up_governance
            follow_up_execution_context["execution_metadata"] = {
                "governance": follow_up_governance
            }

        task = Task(
            id=str(uuid.uuid4()),
            workspace_id=workspace_id,
            message_id=message_id,
            pack_id=playbook_code or "meeting_dispatch",
            task_type="playbook_execution",
            status=TaskStatus.PENDING,
            params={
                "remediation": True,
                "playbook_code": playbook_code,
            },
            execution_context=follow_up_execution_context,
        )
        engine.tasks_store.create_task(task)
        logger.info(
            "GovernanceEngine: follow-up task created id=%s pb=%s round=%d",
            task.id,
            playbook_code,
            remediation_round,
        )
    except Exception as exc:
        logger.warning(
            "GovernanceEngine: follow-up task creation failed (non-fatal): %s",
            exc,
        )


def trigger_follow_up(
    engine: Any,
    *,
    workspace_id: str,
    execution_id: str,
    artifact_id: Optional[str],
    playbook_code: Optional[str],
    eval_result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """Evaluate remediation policy and create follow-up task if warranted."""
    from backend.app.services.orchestration.remediation_policy import (
        RemediationPolicy,
    )

    current_round = 0
    acceptance_tests = None
    task_ir_id = None
    original_message_id = None
    try:
        task = engine.tasks_store.get_task_by_execution_id(execution_id)
        if task:
            context = getattr(task, "execution_context", None) or {}
            current_round = context.get("remediation_round", 0)
            task_ir_id = context.get("task_ir_id")
            original_message_id = getattr(task, "message_id", None)
            governance = resolve_governance_payload(engine, execution_id)
            if isinstance(governance, dict):
                acceptance_tests = governance.get("acceptance_tests")
    except Exception:
        pass

    policy = RemediationPolicy()
    decision = policy.decide(
        eval_result=eval_result,
        current_round=current_round,
        execution_id=execution_id,
        artifact_id=artifact_id,
        playbook_code=playbook_code,
        acceptance_tests=acceptance_tests,
    )
    decision_dict = decision.to_dict()

    if decision.should_follow_up and decision.follow_up_context:
        decision.follow_up_context["task_ir_id"] = task_ir_id
        decision.follow_up_context["original_message_id"] = original_message_id
        create_follow_up_task(
            engine,
            workspace_id=workspace_id,
            playbook_code=playbook_code,
            follow_up_context=decision.follow_up_context,
        )
    return decision_dict
