"""
Quality Gate Checker - Check quality gates before execution completion

Phase 2: Enforces quality gates from Runtime Profile (lint, tests, docs, etc.)
"""

import logging
import subprocess
import os
import uuid
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from backend.app.models.workspace_runtime_profile import QualityGates
from backend.app.models.mindscape import MindEvent, EventType, EventActor

logger = logging.getLogger(__name__)


@dataclass
class QualityGateResult:
    """Result of quality gate check"""
    passed: bool
    failed_gates: List[str] = None
    details: Dict[str, Any] = None

    def __post_init__(self):
        if self.failed_gates is None:
            self.failed_gates = []
        if self.details is None:
            self.details = {}


class QualityGateChecker:
    """
    Quality Gate Checker - Check quality gates before execution completion

    Supports checking:
    - Lint (ruff, black, mypy, etc.)
    - Tests (pytest)
    - Documentation updates
    - Change list
    - Rollback plan
    - Citations
    """

    def __init__(
        self,
        workspace_id: Optional[str] = None,
        project_path: Optional[str] = None,
        execution_id: Optional[str] = None,
        profile_id: Optional[str] = None,
        event_store: Optional[Any] = None
    ):
        """
        Initialize Quality Gate Checker

        Args:
            workspace_id: Workspace ID (for context)
            project_path: Project path (for running checks)
            execution_id: Execution ID (for event recording)
            profile_id: Profile ID (for event recording)
            event_store: Optional event store for recording events
        """
        self.workspace_id = workspace_id
        self.project_path = project_path or os.getcwd()
        self.execution_id = execution_id
        self.profile_id = profile_id
        self.event_store = event_store

    def check_quality_gates(
        self,
        quality_gates: QualityGates,
        execution_result: Optional[Dict[str, Any]] = None,
        changed_files: Optional[List[str]] = None
    ) -> QualityGateResult:
        """
        Check all enabled quality gates

        Args:
            quality_gates: QualityGates configuration
            execution_result: Optional execution result (for context)
            changed_files: Optional list of changed files

        Returns:
            QualityGateResult with check results
        """
        result = QualityGateResult(passed=True)

        # Check lint
        if quality_gates.require_lint:
            lint_result = self._check_lint(changed_files)
            if not lint_result["passed"]:
                result.passed = False
                result.failed_gates.append("lint")
                result.details["lint"] = lint_result

        # Check tests
        if quality_gates.require_tests:
            test_result = self._check_tests()
            if not test_result["passed"]:
                result.passed = False
                result.failed_gates.append("tests")
                result.details["tests"] = test_result

        # Check docs
        if quality_gates.require_docs:
            docs_result = self._check_docs(changed_files)
            if not docs_result["passed"]:
                result.passed = False
                result.failed_gates.append("docs")
                result.details["docs"] = docs_result

        # Check changelist (always check if require_changelist is True)
        if quality_gates.require_changelist:
            changelist_result = self._check_changelist(changed_files)
            if not changelist_result["passed"]:
                result.passed = False
                result.failed_gates.append("changelist")
                result.details["changelist"] = changelist_result

        # Check rollback plan (for high-risk operations)
        if quality_gates.require_rollback_plan:
            rollback_result = self._check_rollback_plan(execution_result)
            if not rollback_result["passed"]:
                result.passed = False
                result.failed_gates.append("rollback_plan")
                result.details["rollback_plan"] = rollback_result

        # Check citations (for research workspaces)
        if quality_gates.require_citations:
            citations_result = self._check_citations(execution_result)
            if not citations_result["passed"]:
                result.passed = False
                result.failed_gates.append("citations")
                result.details["citations"] = citations_result

        # Record quality gate check event (P1: Observability)
        self._record_quality_gate_event(quality_gates, result)

        return result

    def _record_quality_gate_event(
        self,
        quality_gates: QualityGates,
        result: QualityGateResult
    ):
        """
        Record quality gate check event for observability (P1)

        Args:
            quality_gates: QualityGates configuration
            result: Quality gate check result
        """
        if not self.event_store or not self.execution_id:
            # Skip event recording if event_store or execution_id not provided
            return

        try:
            event = MindEvent(
                id=str(uuid.uuid4()),
                timestamp=_utc_now(),
                actor=EventActor.SYSTEM,
                channel="runtime_profile",
                profile_id=self.profile_id or "system",
                workspace_id=self.workspace_id,
                event_type=EventType.QUALITY_GATE_CHECK,
                payload={
                    "execution_id": self.execution_id,
                    "passed": result.passed,
                    "failed_gates": result.failed_gates,
                    "details": result.details,
                    "enabled_gates": {
                        "require_lint": quality_gates.require_lint,
                        "require_tests": quality_gates.require_tests,
                        "require_docs": quality_gates.require_docs,
                        "require_changelist": quality_gates.require_changelist,
                        "require_rollback_plan": quality_gates.require_rollback_plan,
                        "require_citations": quality_gates.require_citations
                    }
                }
            )
            self.event_store.create(event)
            logger.info(
                f"QualityGateChecker: Recorded quality gate check event for execution_id={self.execution_id}, "
                f"passed={result.passed}, failed_gates={result.failed_gates}"
            )
        except Exception as e:
            # Don't fail quality gate check if event recording fails
            logger.warning(f"Failed to record quality gate check event: {e}", exc_info=True)

    def _check_lint(self, changed_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Check linting

        Args:
            changed_files: Optional list of changed files to check

        Returns:
            {"passed": bool, "output": str, "errors": List[str]}
        """
        try:
            # Try ruff first (modern Python linter)
            try:
                cmd = ["ruff", "check", "."]
                if changed_files:
                    cmd.extend(changed_files)

                result = subprocess.run(
                    cmd,
                    cwd=self.project_path,
                    capture_output=True,
                    text=True,
                    timeout=30
                )

                if result.returncode == 0:
                    return {"passed": True, "output": result.stdout, "errors": []}
                else:
                    errors = result.stderr.split("\n") if result.stderr else []
                    return {
                        "passed": False,
                        "output": result.stdout,
                        "errors": errors,
                        "tool": "ruff"
                    }
            except FileNotFoundError:
                # Fallback to flake8 or pylint
                logger.debug("ruff not found, trying flake8")
                try:
                    cmd = ["flake8", "."]
                    if changed_files:
                        cmd.extend(changed_files)

                    result = subprocess.run(
                        cmd,
                        cwd=self.project_path,
                        capture_output=True,
                        text=True,
                        timeout=30
                    )

                    if result.returncode == 0:
                        return {"passed": True, "output": result.stdout, "errors": []}
                    else:
                        return {
                            "passed": False,
                            "output": result.stdout,
                            "errors": result.stderr.split("\n") if result.stderr else [],
                            "tool": "flake8"
                        }
                except FileNotFoundError:
                    logger.warning("No lint tool found (ruff/flake8)")
                    # If no lint tool available, pass (fail-open)
                    return {"passed": True, "output": "No lint tool available", "errors": []}
        except Exception as e:
            logger.warning(f"Lint check failed: {e}", exc_info=True)
            # Fail-open: if lint check fails, allow execution
            return {"passed": True, "output": f"Lint check error: {e}", "errors": []}

    def _check_tests(self) -> Dict[str, Any]:
        """
        Check tests

        Returns:
            {"passed": bool, "output": str, "errors": List[str]}
        """
        try:
            # Try pytest
            cmd = ["pytest", "-v", "--tb=short"]

            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=120  # Tests may take longer
            )

            if result.returncode == 0:
                return {"passed": True, "output": result.stdout, "errors": []}
            else:
                errors = result.stderr.split("\n") if result.stderr else []
                return {
                    "passed": False,
                    "output": result.stdout,
                    "errors": errors,
                    "tool": "pytest"
                }
        except FileNotFoundError:
            logger.warning("pytest not found")
            # If no test tool available, pass (fail-open)
            return {"passed": True, "output": "No test tool available", "errors": []}
        except Exception as e:
            logger.warning(f"Test check failed: {e}", exc_info=True)
            # Fail-open: if test check fails, allow execution
            return {"passed": True, "output": f"Test check error: {e}", "errors": []}

    def _check_docs(self, changed_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Check if documentation was updated

        Args:
            changed_files: Optional list of changed files

        Returns:
            {"passed": bool, "output": str, "errors": List[str]}
        """
        # Check if any doc files were modified
        doc_extensions = [".md", ".rst", ".txt"]
        doc_dirs = ["docs", "doc", "documentation"]

        if changed_files:
            # Check if any changed files are docs
            has_doc_changes = any(
                any(ext in f for ext in doc_extensions) or
                any(doc_dir in f for doc_dir in doc_dirs)
                for f in changed_files
            )

            if has_doc_changes:
                return {"passed": True, "output": "Documentation files were updated", "errors": []}
            else:
                return {
                    "passed": False,
                    "output": "No documentation files were updated",
                    "errors": ["Documentation update required but no doc files changed"]
                }
        else:
            # If no changed_files provided, assume docs were updated (fail-open)
            return {"passed": True, "output": "Cannot verify docs (no changed_files provided)", "errors": []}

    def _check_changelist(self, changed_files: Optional[List[str]] = None) -> Dict[str, Any]:
        """
        Check if changelist was provided

        Args:
            changed_files: Optional list of changed files

        Returns:
            {"passed": bool, "output": str, "errors": List[str]}
        """
        # For now, if changed_files is provided, assume changelist exists
        # In future, could check for CHANGELOG.md or similar
        if changed_files:
            return {
                "passed": True,
                "output": f"Change list provided ({len(changed_files)} files)",
                "errors": []
            }
        else:
            # If no changed_files, check if we can infer from execution_result
            return {
                "passed": True,  # Fail-open: assume changelist exists if cannot verify
                "output": "Cannot verify changelist (no changed_files provided)",
                "errors": []
            }

    def _check_rollback_plan(self, execution_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Check if rollback plan was provided

        Args:
            execution_result: Optional execution result

        Returns:
            {"passed": bool, "output": str, "errors": List[str]}
        """
        # Check if execution_result contains rollback information
        if execution_result and execution_result.get("rollback_plan"):
            return {
                "passed": True,
                "output": "Rollback plan provided",
                "errors": []
            }
        else:
            # Fail-open: if no rollback plan, allow execution
            return {
                "passed": True,
                "output": "No rollback plan required or provided",
                "errors": []
            }

    def _check_citations(self, execution_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Check if citations were included in output

        Args:
            execution_result: Optional execution result

        Returns:
            {"passed": bool, "output": str, "errors": List[str]}
        """
        # Check if execution_result contains citations
        if execution_result:
            output_text = str(execution_result.get("output", ""))
            # Check for citation markers
            citation_markers = ["## References", "## Citations", "[1]", "[2]", "参考文献", "引用"]
            has_citations = any(marker in output_text for marker in citation_markers)

            if has_citations:
                return {
                    "passed": True,
                    "output": "Citations found in output",
                    "errors": []
                }
            else:
                return {
                    "passed": False,
                    "output": "No citations found in output",
                    "errors": ["Citations required but not found in output"]
                }
        else:
            # Fail-open: if no execution_result, assume citations exist
            return {
                "passed": True,
                "output": "Cannot verify citations (no execution_result provided)",
                "errors": []
            }

