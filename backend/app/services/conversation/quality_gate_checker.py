"""Quality gate checker facade."""

import os
from typing import Any, Dict, List, Optional

from backend.app.models.workspace_runtime_profile import QualityGates
from backend.app.services.conversation.quality_gate_checker_core import (
    QualityGateResult,
    check_changelist,
    check_citations,
    check_docs,
    check_lint,
    check_quality_gates as check_quality_gates_helper,
    check_rollback_plan,
    check_tests,
    record_quality_gate_event,
    utc_now as _utc_now,
)


class QualityGateChecker:
    """Checks runtime profile quality gates before execution completion."""

    def __init__(
        self,
        workspace_id: Optional[str] = None,
        project_path: Optional[str] = None,
        execution_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        event_store: Optional[Any] = None,
    ):
        self.workspace_id = workspace_id
        self.project_path = project_path or os.getcwd()
        self.execution_id = execution_id
        self.profile_id = profile_id
        self.event_store = event_store

    def check_quality_gates(
        self,
        quality_gates: QualityGates,
        execution_result: Optional[Dict[str, Any]] = None,
        changed_files: Optional[List[str]] = None,
    ) -> QualityGateResult:
        """Check all enabled quality gates."""
        return check_quality_gates_helper(
            checker=self,
            quality_gates=quality_gates,
            execution_result=execution_result,
            changed_files=changed_files,
        )

    def _record_quality_gate_event(
        self,
        quality_gates: QualityGates,
        result: QualityGateResult,
    ):
        return record_quality_gate_event(
            event_store=self.event_store,
            execution_id=self.execution_id,
            profile_id=self.profile_id,
            workspace_id=self.workspace_id,
            quality_gates=quality_gates,
            result=result,
        )

    def _check_lint(self, changed_files: Optional[List[str]] = None) -> Dict[str, Any]:
        return check_lint(
            project_path=self.project_path,
            changed_files=changed_files,
        )

    def _check_tests(self) -> Dict[str, Any]:
        return check_tests(project_path=self.project_path)

    def _check_docs(self, changed_files: Optional[List[str]] = None) -> Dict[str, Any]:
        return check_docs(changed_files=changed_files)

    def _check_changelist(
        self,
        changed_files: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        return check_changelist(changed_files=changed_files)

    def _check_rollback_plan(
        self,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return check_rollback_plan(execution_result=execution_result)

    def _check_citations(
        self,
        execution_result: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return check_citations(execution_result=execution_result)
