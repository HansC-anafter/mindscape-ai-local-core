"""Plan executor completion gates."""

import logging
from typing import List

logger = logging.getLogger(__name__)


def check_definition_of_done(
    *,
    runtime_profile,
    stop_conditions,
    workspace,
    results,
) -> None:
    if not stop_conditions or not stop_conditions.definition_of_done:
        logger.info("DefinitionOfDone: All criteria passed")
        return

    logger.info(
        f"StopConditions: Checking definition_of_done: {stop_conditions.definition_of_done}"
    )
    changed_files = collect_changed_files(results)
    definition_of_done_passed = True
    for criterion in stop_conditions.definition_of_done:
        criterion_lower = criterion.lower().strip()
        if criterion_lower == "lint passed":
            definition_of_done_passed = (
                check_lint_criterion(runtime_profile, workspace, changed_files)
                and definition_of_done_passed
            )
        elif criterion_lower == "tests passed":
            definition_of_done_passed = (
                check_tests_criterion(runtime_profile, workspace)
                and definition_of_done_passed
            )
        elif criterion_lower == "docs updated":
            definition_of_done_passed = (
                check_docs_criterion(changed_files) and definition_of_done_passed
            )
        else:
            logger.warning(
                f"DefinitionOfDone: Unknown criterion '{criterion}', treating as passed"
            )

    if not definition_of_done_passed:
        logger.error(
            "DefinitionOfDone: Not all criteria passed. Execution marked as incomplete."
        )
        raise ValueError(
            f"DefinitionOfDone not met. Failed criteria: {stop_conditions.definition_of_done}. "
            "Execution cannot be marked as complete."
        )
    logger.info("DefinitionOfDone: All criteria passed")


def collect_changed_files(results) -> List[str]:
    changed_files = []
    for executed_task in results.get("executed_tasks", []):
        if isinstance(executed_task, dict) and executed_task.get("changed_files"):
            changed_files.extend(executed_task["changed_files"])
    return changed_files


def check_lint_criterion(runtime_profile, workspace, changed_files) -> bool:
    if not runtime_profile or not runtime_profile.quality_gates:
        logger.warning(
            "DefinitionOfDone: 'lint passed' required but quality_gates not configured"
        )
        return False
    from backend.app.services.conversation.quality_gate_checker import (
        QualityGateChecker,
    )

    quality_checker = QualityGateChecker(
        workspace_id=workspace.id if workspace else None,
        project_path=None,
    )
    lint_result = quality_checker._check_lint(changed_files)
    if not lint_result.get("passed", False):
        logger.warning(
            f"DefinitionOfDone: 'lint passed' failed: {lint_result.get('errors', [])}"
        )
        return False
    return True


def check_tests_criterion(runtime_profile, workspace) -> bool:
    if not runtime_profile or not runtime_profile.quality_gates:
        logger.warning(
            "DefinitionOfDone: 'tests passed' required but quality_gates not configured"
        )
        return False
    from backend.app.services.conversation.quality_gate_checker import (
        QualityGateChecker,
    )

    quality_checker = QualityGateChecker(
        workspace_id=workspace.id if workspace else None,
        project_path=None,
    )
    test_result = quality_checker._check_tests()
    if not test_result.get("passed", False):
        logger.warning(
            f"DefinitionOfDone: 'tests passed' failed: {test_result.get('errors', [])}"
        )
        return False
    return True


def check_docs_criterion(changed_files) -> bool:
    doc_extensions = [".md", ".rst", ".txt"]
    doc_dirs = ["docs", "doc", "documentation"]
    has_doc_changes = bool(changed_files) and any(
        any(ext in file_name for ext in doc_extensions)
        or any(doc_dir in file_name for doc_dir in doc_dirs)
        for file_name in changed_files
    )
    if not has_doc_changes:
        logger.warning(
            "DefinitionOfDone: 'docs updated' failed: No documentation files were modified"
        )
        return False
    return True


def check_quality_gates(
    *,
    runtime_profile,
    workspace,
    results,
    orchestration_state,
) -> None:
    if not runtime_profile or not runtime_profile.quality_gates:
        return
    try:
        from backend.app.services.conversation.quality_gate_checker import (
            QualityGateChecker,
        )
        from backend.app.services.stores.postgres.events_store import (
            PostgresEventsStore,
        )

        changed_files = collect_changed_files(results)
        execution_id_for_quality = orchestration_state.primary_execution_id
        if not execution_id_for_quality and results.get("executed_tasks"):
            first_task = results["executed_tasks"][0]
            if isinstance(first_task, dict):
                execution_id_for_quality = first_task.get("execution_id")

        quality_checker = QualityGateChecker(
            workspace_id=workspace.id if workspace else None,
            project_path=None,
            execution_id=execution_id_for_quality,
            profile_id=getattr(runtime_profile, "profile_id", None),
            event_store=PostgresEventsStore(),
        )
        quality_result = quality_checker.check_quality_gates(
            quality_gates=runtime_profile.quality_gates,
            execution_result={"executed_tasks": results.get("executed_tasks", [])},
            changed_files=changed_files if changed_files else None,
        )
        if not quality_result.passed:
            logger.error(
                f"QualityGates: Failed gates: {quality_result.failed_gates}. "
                f"Details: {quality_result.details}"
            )
            failed_gates_str = ", ".join(quality_result.failed_gates)
            raise ValueError(
                f"QualityGates not passed. Failed gates: {failed_gates_str}. "
                f"Details: {quality_result.details}. "
                "Execution cannot be marked as complete."
            )
        logger.info("QualityGates: All checks passed")
    except ValueError:
        raise
    except Exception as exc:
        logger.error(f"QualityGates check failed: {exc}", exc_info=True)
        raise ValueError(
            f"QualityGates check encountered an error: {exc}. "
            "Execution cannot be marked as complete."
        ) from exc
