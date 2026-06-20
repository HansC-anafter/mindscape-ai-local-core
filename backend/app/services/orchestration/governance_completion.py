"""Completion orchestration helper for ``GovernanceEngine``."""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def process_completion(
    engine: Any,
    *,
    workspace_id: str,
    execution_id: str,
    result_data: Dict[str, Any],
    storage_base_path: Optional[str] = None,
    artifacts_dirname: str = "artifacts",
    thread_id: Optional[str] = None,
    project_id: Optional[str] = None,
    task_id: Optional[str] = None,
    playbook_code: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Land execution results through the governance facade."""
    if not playbook_code:
        playbook_code = engine._resolve_playbook_code(execution_id)

    logger.info(
        "GovernanceEngine.process_completion: exec=%s pb=%s ws=%s",
        execution_id,
        playbook_code or "(unknown)",
        workspace_id,
    )

    landing_result = engine.landing.land_result(
        workspace_id=workspace_id,
        execution_id=execution_id,
        result_data=result_data,
        storage_base_path=storage_base_path,
        artifacts_dirname=artifacts_dirname,
        thread_id=thread_id,
        project_id=project_id,
        task_id=task_id,
    )

    if landing_result:
        logger.info(
            "GovernanceEngine: landing succeeded exec=%s artifact=%s",
            execution_id,
            getattr(landing_result, "artifact_id", None),
        )
    else:
        logger.warning(
            "GovernanceEngine: landing returned None exec=%s",
            execution_id,
        )

    parsed_output = None
    if engine.adapter:
        try:
            parsed_output = engine.adapter.parse_result(
                result_data=result_data,
                playbook_code=playbook_code,
            )
        except Exception as exc:
            logger.warning(
                "GovernanceEngine: parse_result sidecar failed (non-fatal): %s",
                exc,
            )

    artifact_id = getattr(landing_result, "artifact_id", None) if landing_result else None
    if parsed_output and artifact_id:
        engine._backfill_provenance(
            artifact_id=artifact_id,
            execution_id=execution_id,
            playbook_code=playbook_code,
            parsed_output=parsed_output,
        )

    artifact_registry_id = None
    resolved_project_id = engine._resolve_project_id(
        execution_id=execution_id,
        project_id=project_id,
    )
    if (
        resolved_project_id
        and artifact_id
        and landing_result
        and getattr(landing_result, "artifact_dir", None)
    ):
        registry_entry = engine._register_project_artifact(
            project_id=resolved_project_id,
            artifact_id=artifact_id,
            artifact_path=landing_result.artifact_dir,
            artifact_type="data",
            created_by=playbook_code or "unknown_playbook",
        )
        artifact_registry_id = getattr(registry_entry, "id", None)

    eval_result_dict = None
    correctness_signals = None
    try:
        from backend.app.services.orchestration.acceptance_evaluator import (
            AcceptanceEvaluator,
        )

        acceptance_tests = engine._resolve_acceptance_tests(execution_id)
        evaluator = AcceptanceEvaluator()
        eval_result = evaluator.evaluate(
            result_data=result_data,
            parsed_output=parsed_output,
            acceptance_tests=acceptance_tests,
            playbook_code=playbook_code,
        )
        eval_result_dict = eval_result.to_dict()
    except Exception as exc:
        logger.warning(
            "GovernanceEngine: AcceptanceEvaluator failed (non-fatal): %s",
            exc,
        )

    remediation_decision = None
    if eval_result_dict and not eval_result_dict.get("passed"):
        try:
            remediation_decision = engine._trigger_follow_up(
                workspace_id=workspace_id,
                execution_id=execution_id,
                artifact_id=artifact_id,
                playbook_code=playbook_code,
                eval_result=eval_result_dict,
            )
        except Exception as exc:
            logger.warning(
                "GovernanceEngine: follow-up trigger failed (non-fatal): %s",
                exc,
            )

    if eval_result_dict:
        correctness_signals = engine._sync_correctness_signals(
            execution_id=execution_id,
            artifact_id=artifact_id,
            playbook_code=playbook_code,
            eval_summary=eval_result_dict,
            remediation=remediation_decision,
        )
        if artifact_id:
            engine._backfill_eval_summary(
                artifact_id=artifact_id,
                eval_summary=eval_result_dict,
            )

    return {
        "success": landing_result is not None,
        "execution_id": execution_id,
        "artifact_id": artifact_id,
        "artifact_registry_id": artifact_registry_id,
        "parsed_output": parsed_output,
        "eval_result": eval_result_dict,
        "correctness_signals": correctness_signals,
        "remediation": remediation_decision,
    }
