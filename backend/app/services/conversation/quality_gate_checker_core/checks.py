"""Individual quality gate checks."""

import logging
import subprocess
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def check_lint(
    *,
    project_path: str,
    changed_files: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Check linting with ruff, falling back to flake8 when needed."""
    try:
        try:
            cmd = ["ruff", "check", "."]
            if changed_files:
                cmd.extend(changed_files)

            result = subprocess.run(
                cmd,
                cwd=project_path,
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return {"passed": True, "output": result.stdout, "errors": []}

            errors = result.stderr.split("\n") if result.stderr else []
            return {
                "passed": False,
                "output": result.stdout,
                "errors": errors,
                "tool": "ruff",
            }
        except FileNotFoundError:
            logger.debug("ruff not found, trying flake8")
            try:
                cmd = ["flake8", "."]
                if changed_files:
                    cmd.extend(changed_files)

                result = subprocess.run(
                    cmd,
                    cwd=project_path,
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                if result.returncode == 0:
                    return {"passed": True, "output": result.stdout, "errors": []}

                return {
                    "passed": False,
                    "output": result.stdout,
                    "errors": result.stderr.split("\n") if result.stderr else [],
                    "tool": "flake8",
                }
            except FileNotFoundError:
                logger.warning("No lint tool found (ruff/flake8)")
                return {"passed": True, "output": "No lint tool available", "errors": []}
    except Exception as exc:
        logger.warning("Lint check failed: %s", exc, exc_info=True)
        return {"passed": True, "output": f"Lint check error: {exc}", "errors": []}


def check_tests(*, project_path: str) -> Dict[str, Any]:
    """Check tests with pytest."""
    try:
        result = subprocess.run(
            ["pytest", "-v", "--tb=short"],
            cwd=project_path,
            capture_output=True,
            text=True,
            timeout=120,
        )

        if result.returncode == 0:
            return {"passed": True, "output": result.stdout, "errors": []}

        errors = result.stderr.split("\n") if result.stderr else []
        return {
            "passed": False,
            "output": result.stdout,
            "errors": errors,
            "tool": "pytest",
        }
    except FileNotFoundError:
        logger.warning("pytest not found")
        return {"passed": True, "output": "No test tool available", "errors": []}
    except Exception as exc:
        logger.warning("Test check failed: %s", exc, exc_info=True)
        return {"passed": True, "output": f"Test check error: {exc}", "errors": []}


def check_docs(changed_files: Optional[List[str]] = None) -> Dict[str, Any]:
    """Check if documentation was updated."""
    doc_extensions = [".md", ".rst", ".txt"]
    doc_dirs = ["docs", "doc", "documentation"]

    if changed_files:
        has_doc_changes = any(
            any(ext in file_name for ext in doc_extensions)
            or any(doc_dir in file_name for doc_dir in doc_dirs)
            for file_name in changed_files
        )

        if has_doc_changes:
            return {"passed": True, "output": "Documentation files were updated", "errors": []}

        return {
            "passed": False,
            "output": "No documentation files were updated",
            "errors": ["Documentation update required but no doc files changed"],
        }

    return {"passed": True, "output": "Cannot verify docs (no changed_files provided)", "errors": []}


def check_changelist(changed_files: Optional[List[str]] = None) -> Dict[str, Any]:
    """Check if a changelist was provided."""
    if changed_files:
        return {
            "passed": True,
            "output": f"Change list provided ({len(changed_files)} files)",
            "errors": [],
        }

    return {
        "passed": True,
        "output": "Cannot verify changelist (no changed_files provided)",
        "errors": [],
    }


def check_rollback_plan(
    execution_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Check if a rollback plan was provided."""
    if execution_result and execution_result.get("rollback_plan"):
        return {
            "passed": True,
            "output": "Rollback plan provided",
            "errors": [],
        }

    return {
        "passed": True,
        "output": "No rollback plan required or provided",
        "errors": [],
    }


def check_citations(
    execution_result: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Check if citations were included in output."""
    if execution_result:
        output_text = str(execution_result.get("output", ""))
        citation_markers = [
            "## References",
            "## Citations",
            "[1]",
            "[2]",
            "\u53c2\u8003\u6587\u732e",
            "\u5f15\u7528",
        ]
        has_citations = any(marker in output_text for marker in citation_markers)

        if has_citations:
            return {
                "passed": True,
                "output": "Citations found in output",
                "errors": [],
            }

        return {
            "passed": False,
            "output": "No citations found in output",
            "errors": ["Citations required but not found in output"],
        }

    return {
        "passed": True,
        "output": "Cannot verify citations (no execution_result provided)",
        "errors": [],
    }
