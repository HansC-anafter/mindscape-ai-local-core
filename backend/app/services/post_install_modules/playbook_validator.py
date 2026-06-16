"""
Playbook Validator

Validates installed playbooks:
1. Structure validation (via script)
2. Direct tool call test (backend simulation, no LLM)
"""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Callable

from backend.app.services.runtime_contract_paths import build_validation_pythonpath
from backend.app.services.post_install_modules.playbook_structure_validation import (
    PlaybookStructureValidationMixin,
)

logger = logging.getLogger(__name__)


class PlaybookValidator(PlaybookStructureValidationMixin):
    """Validates installed playbooks"""

    def __init__(
        self,
        local_core_root: Path,
        capabilities_dir: Path,
        validate_tools_direct_call_func: Optional[Callable] = None
    ):
        """
        Initialize playbook validator

        Args:
            local_core_root: Local-core project root directory
            capabilities_dir: Capabilities directory
            validate_tools_direct_call_func: Function to validate tools via direct call
        """
        self.local_core_root = local_core_root
        self.capabilities_dir = capabilities_dir
        self._validate_tools_direct_call = validate_tools_direct_call_func

    def _build_subprocess_env(self) -> Dict[str, str]:
        return {
            **dict(os.environ),
            "LLM_MOCK": "false",
            "BASE_URL": self._default_base_url(),
            "PYTHONPATH": build_validation_pythonpath(
                self.local_core_root,
                self.capabilities_dir,
            ),
            "CAPABILITIES_PATH": str(self.capabilities_dir),
        }

    def _default_base_url(self) -> str:
        try:
            from backend.app.services.service_endpoint_registry import service_endpoint_registry

            return (
                service_endpoint_registry.get_endpoint_url(
                    "local_core.execution_api", "host_public"
                )
                or ""
            )
        except Exception:
            return ""

    def validate_installed_playbooks(
        self,
        capability_code: str,
        manifest: Dict,
        result
    ):
        """
        Validate installed playbooks

        Args:
            capability_code: Capability code
            manifest: Parsed manifest dictionary
            result: InstallResult object
        """
        playbooks_config = manifest.get('playbooks', [])
        if not playbooks_config:
            return

        validation_results = {
            "validated": [],
            "failed": [],
            "skipped": []
        }
        tool_model_preload_cache: Dict[str, str] = {}
        playbook_codes = {
            pb_config.get("code")
            for pb_config in playbooks_config
            if pb_config.get("code")
        }

        # Check if validation script exists
        validate_script = self.local_core_root / "scripts" / "validate_playbooks.py"
        if not validate_script.exists():
            logger.warning("validate_playbooks.py not found, skipping playbook validation")
            result.add_warning("Playbook validation skipped: script not found")
            return

        structure_results = self._validate_capability_structure(
            capability_code,
            playbook_codes,
            validate_script,
            validation_results,
        )

        for pb_config in playbooks_config:
            playbook_code = pb_config.get('code')
            if not playbook_code:
                continue

            structure_valid = structure_results.get(playbook_code)
            if structure_valid is None:
                structure_valid = self._validate_structure(
                    playbook_code,
                    capability_code,
                    validate_script,
                    validation_results
                )

            # 2. If structure validation passed, perform direct tool call test
            if structure_valid and self._validate_tools_direct_call:
                self._validate_tool_calls(
                    playbook_code,
                    capability_code,
                    validation_results,
                    tool_model_preload_cache,
                )
            elif structure_valid:
                # Structure valid but no tool validation function provided
                validation_results["validated"].append(playbook_code)
                logger.info(f"Playbook {playbook_code} structure validated (tool call test skipped)")

        # Add validation results to result
        result.playbook_validation = validation_results

        # Process validation results and add to result
        self._process_validation_results(validation_results, result)

    def _validate_tool_calls(
        self,
        playbook_code: str,
        capability_code: str,
        validation_results: Dict,
        tool_model_preload_cache: Dict[str, str],
    ):
        """Validate tool calls"""
        try:
            tool_test_errors, tool_test_warnings = self._validate_tools_direct_call(
                playbook_code,
                capability_code,
                tool_model_preload_cache,
            )

            # Add warnings for optional dependency issues
            if tool_test_warnings:
                for warning in tool_test_warnings:
                    validation_results["warnings"] = validation_results.get("warnings", [])
                    validation_results["warnings"].append({
                        "playbook": playbook_code,
                        "warning": warning
                    })
                    logger.warning(f"Playbook {playbook_code} tool validation warning: {warning}")

            if tool_test_errors:
                # Check if errors are due to missing optional dependencies
                optional_dep_errors, critical_errors = self._categorize_tool_errors(tool_test_errors)

                # Only critical errors are treated as failures
                if critical_errors:
                    error_msg = self._format_critical_errors(critical_errors)
                    validation_results["failed"].append({
                        "playbook": playbook_code,
                        "error": f"Tool call test failed: {error_msg}"
                    })
                    logger.error(f"Playbook {playbook_code} tool call test failed: {error_msg}")
                elif optional_dep_errors:
                    # Missing optional dependencies are treated as warnings
                    warning_msg = self._format_optional_dep_warning(optional_dep_errors)
                    validation_results["warnings"] = validation_results.get("warnings", [])
                    validation_results["warnings"].append({
                        "playbook": playbook_code,
                        "warning": warning_msg
                    })
                    logger.warning(f"Playbook {playbook_code} tool validation warning: {warning_msg}")
            else:
                validation_results["validated"].append(playbook_code)
                logger.info(f"Playbook {playbook_code} validated successfully (structure + tool call test)")
        except Exception as e:
            # Tool call test itself failed (e.g., import failure), record as failure
            validation_results["failed"].append({
                "playbook": playbook_code,
                "error": f"Tool call test exception: {str(e)}"
            })
            logger.error(f"Playbook {playbook_code} tool call test exception: {e}")

    def _categorize_tool_errors(self, errors: List[str]) -> Tuple[List[str], List[str]]:
        """Categorize tool errors into optional dependency errors and critical errors"""
        optional_dep_errors = []
        critical_errors = []
        for err in errors:
            # Check if error is about missing module (optional dependency)
            if "No module named" in err and any(dep in err.lower() for dep in ['bs4', 'beautifulsoup', 'httpx', 'requests']):
                optional_dep_errors.append(err)
            else:
                critical_errors.append(err)
        return optional_dep_errors, critical_errors

    def _format_critical_errors(self, critical_errors: List[str]) -> str:
        """Format critical error messages"""
        if len(critical_errors) == 1:
            return critical_errors[0]
        else:
            error_msg = f"{len(critical_errors)} tool validation errors: " + "; ".join(critical_errors[:3])
            if len(critical_errors) > 3:
                error_msg += f" (and {len(critical_errors) - 3} more)"
            return error_msg

    def _format_optional_dep_warning(self, optional_dep_errors: List[str]) -> str:
        """Format optional dependency warning messages"""
        dep_names = []
        for e in optional_dep_errors:
            if "'" in e:
                parts = e.split("'")
                if len(parts) >= 2:
                    dep_names.append(parts[1])
            else:
                dep_names.append('unknown')
        return f"Missing optional dependencies: {', '.join(set(dep_names))}"

    def _process_validation_results(self, validation_results: Dict, result):
        """Process validation results and add to result"""
        # Add errors for failed validations
        if validation_results["failed"]:
            failed_playbooks = []
            warnings_for_missing_deps = []
            for f in validation_results["failed"]:
                playbook = f['playbook']
                error = f.get('error', '')
                # Check if failure is due to missing external dependency tools
                if 'backend not found' in error and ('wordpress.' in error or 'seo.' in error):
                    warnings_for_missing_deps.append(
                        f"{playbook} (missing external dependencies: {error.split('Tool')[1] if 'Tool' in error else 'external tools'})"
                    )
                else:
                    failed_playbooks.append(playbook)

            # Only non-external dependency failures are treated as errors
            if failed_playbooks:
                error_msg = f"Playbook validation failed for: {failed_playbooks}"
                result.add_error(error_msg)
                logger.error(error_msg)

            # Missing external dependencies are treated as warnings
            if warnings_for_missing_deps:
                warning_msg = f"Playbook validation warnings (missing external dependencies): {warnings_for_missing_deps}"
                result.add_warning(warning_msg)
                logger.warning(warning_msg)

        # Add warnings for skipped validations
        if validation_results["skipped"]:
            result.add_warning(
                f"Playbook validation skipped for: {validation_results['skipped']}"
            )
