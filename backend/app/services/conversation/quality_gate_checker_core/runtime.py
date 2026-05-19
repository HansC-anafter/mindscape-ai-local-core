"""Runtime orchestration for quality gate checks."""

from typing import Any, Dict, List, Optional

from backend.app.models.workspace_runtime_profile import QualityGates
from backend.app.services.conversation.quality_gate_checker_core.models import (
    QualityGateResult,
)


def check_quality_gates(
    *,
    checker,
    quality_gates: QualityGates,
    execution_result: Optional[Dict[str, Any]] = None,
    changed_files: Optional[List[str]] = None,
) -> QualityGateResult:
    """Check all enabled quality gates."""
    result = QualityGateResult(passed=True)

    if quality_gates.require_lint:
        lint_result = checker._check_lint(changed_files)
        if not lint_result["passed"]:
            result.passed = False
            result.failed_gates.append("lint")
            result.details["lint"] = lint_result

    if quality_gates.require_tests:
        test_result = checker._check_tests()
        if not test_result["passed"]:
            result.passed = False
            result.failed_gates.append("tests")
            result.details["tests"] = test_result

    if quality_gates.require_docs:
        docs_result = checker._check_docs(changed_files)
        if not docs_result["passed"]:
            result.passed = False
            result.failed_gates.append("docs")
            result.details["docs"] = docs_result

    if quality_gates.require_changelist:
        changelist_result = checker._check_changelist(changed_files)
        if not changelist_result["passed"]:
            result.passed = False
            result.failed_gates.append("changelist")
            result.details["changelist"] = changelist_result

    if quality_gates.require_rollback_plan:
        rollback_result = checker._check_rollback_plan(execution_result)
        if not rollback_result["passed"]:
            result.passed = False
            result.failed_gates.append("rollback_plan")
            result.details["rollback_plan"] = rollback_result

    if quality_gates.require_citations:
        citations_result = checker._check_citations(execution_result)
        if not citations_result["passed"]:
            result.passed = False
            result.failed_gates.append("citations")
            result.details["citations"] = citations_result

    checker._record_quality_gate_event(quality_gates, result)

    return result
