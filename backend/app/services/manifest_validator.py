"""
Manifest Validator

包装本地 validate_manifest.py 执行与输出解析；可注入跳过策略。
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Tuple, List

logger = logging.getLogger(__name__)


class ManifestValidator:
    """Validate manifest using local validate_manifest.py script"""

    def __init__(self, local_core_root: Path):
        """
        Initialize validator

        Args:
            local_core_root: Local-core project root directory
        """
        self.local_core_root = local_core_root
        self.validate_script = local_core_root / "scripts" / "ci" / "validate_manifest.py"

    def validate(
        self,
        manifest_path: Path,
        cap_dir: Path,
        skip_validation: bool = False
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate manifest using local validate_manifest.py script

        Args:
            manifest_path: Path to manifest.yaml
            cap_dir: Capability directory
            skip_validation: Whether to skip validation (from env var)

        Returns:
            (is_valid, errors, warnings)
        """
        if skip_validation:
            logger.warning("Manifest validation skipped (MINDSCAPE_SKIP_VALIDATION=1)")
            return True, [], []

        if not self.validate_script.exists():
            error_msg = f"Local validation script not found: {self.validate_script}. Cannot validate manifest."
            logger.error(error_msg)
            return False, [error_msg], []

        try:
            # Run local validation script
            # validate_manifest.py accepts capability directory path as argument
            result = subprocess.run(
                [sys.executable, str(self.validate_script), str(cap_dir)],
                cwd=str(self.local_core_root),
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Parse warnings (validation passed but may have warnings)
                warnings = []
                for line in result.stdout.split('\n'):
                    if line.strip() and (
                        '⚠️' in line or 'WARNING' in line or 'warning' in line.lower()
                    ):
                        warnings.append(line.strip())
                return True, [], warnings
            else:
                # Validation failed: parse errors and warnings
                errors = []
                warnings = []

                # Parse output (script uses specific format)
                for line in result.stdout.split('\n'):
                    line = line.strip()
                    if not line:
                        continue
                    if (
                        '❌' in line
                        or 'ERROR' in line
                        or 'error' in line.lower()
                        or 'failed' in line.lower()
                    ):
                        errors.append(line)
                    elif 'WARNING' in line or 'warning' in line.lower():
                        warnings.append(line)

                # If no errors parsed from stdout, check stderr
                if not errors and result.stderr:
                    errors.append(result.stderr.strip())
                elif not errors:
                    # If validation failed but no clear error message, use generic error
                    errors.append("Manifest validation failed (see output for details)")

                # Log detailed output for debugging
                if result.stdout:
                    logger.debug(f"Validation output:\n{result.stdout}")
                if result.stderr:
                    logger.debug(f"Validation stderr:\n{result.stderr}")

                return False, errors, warnings

        except subprocess.TimeoutExpired:
            error_msg = "Validation script timed out after 30 seconds"
            logger.error(error_msg)
            return False, [error_msg], []
        except Exception as e:
            error_msg = f"Failed to run validation script: {e}"
            logger.error(error_msg)
            return False, [error_msg], []

    def should_block_installation(self, is_valid: bool, errors: List[str]) -> bool:
        """
        Determine if installation should be blocked based on validation result

        Args:
            is_valid: Whether validation passed
            errors: List of validation errors

        Returns:
            True if installation should be blocked
        """
        if is_valid:
            return False

        # Check if skip validation is enabled
        skip_validation = os.getenv("MINDSCAPE_SKIP_VALIDATION", "0") == "1"
        if skip_validation:
            logger.warning("Validation failed but continuing due to MINDSCAPE_SKIP_VALIDATION=1")
            return False

        # Block installation by default if validation failed
        logger.error("Installation blocked due to manifest validation failure. Set MINDSCAPE_SKIP_VALIDATION=1 to override (not recommended).")
        return True

