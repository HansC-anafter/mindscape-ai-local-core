"""
Syntax checker for sandbox files

Provides TypeScript and other language syntax checking.
"""

import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)


class SandboxSyntaxChecker:
    """
    Syntax checker for sandbox files

    Provides syntax checking for TypeScript, JavaScript, and other languages.
    """

    @staticmethod
    async def check_typescript(
        file_path: str,
        sandbox_path: Path
    ) -> Dict[str, Any]:
        """
        Check TypeScript syntax

        Args:
            file_path: Path to TypeScript file
            sandbox_path: Path to sandbox directory

        Returns:
            Dictionary with check results:
            - valid: True if syntax is valid
            - errors: List of error messages
            - warnings: List of warning messages
        """
        try:
            full_path = sandbox_path / file_path
            if not full_path.exists():
                return {
                    "valid": False,
                    "errors": [f"File not found: {file_path}"],
                    "warnings": []
                }

            result = subprocess.run(
                ["npx", "tsc", "--noEmit", str(full_path)],
                cwd=str(sandbox_path),
                capture_output=True,
                text=True,
                timeout=30
            )

            errors = []
            warnings = []

            if result.returncode != 0:
                for line in result.stderr.split("\n"):
                    if line.strip():
                        if "error" in line.lower():
                            errors.append(line.strip())
                        elif "warning" in line.lower():
                            warnings.append(line.strip())

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings
            }

        except subprocess.TimeoutExpired:
            return {
                "valid": False,
                "errors": ["TypeScript check timeout"],
                "warnings": []
            }
        except Exception as e:
            logger.error(f"Failed to check TypeScript syntax: {e}")
            return {
                "valid": False,
                "errors": [str(e)],
                "warnings": []
            }

    @staticmethod
    async def check_javascript(
        file_path: str,
        sandbox_path: Path
    ) -> Dict[str, Any]:
        """
        Check JavaScript syntax using ESLint

        Args:
            file_path: Path to JavaScript file
            sandbox_path: Path to sandbox directory

        Returns:
            Dictionary with check results
        """
        try:
            full_path = sandbox_path / file_path
            if not full_path.exists():
                return {
                    "valid": False,
                    "errors": [f"File not found: {file_path}"],
                    "warnings": []
                }

            result = subprocess.run(
                ["npx", "eslint", str(full_path)],
                cwd=str(sandbox_path),
                capture_output=True,
                text=True,
                timeout=30
            )

            errors = []
            warnings = []

            if result.returncode != 0:
                for line in result.stdout.split("\n"):
                    if line.strip():
                        if "error" in line.lower():
                            errors.append(line.strip())
                        elif "warning" in line.lower():
                            warnings.append(line.strip())

            return {
                "valid": len(errors) == 0,
                "errors": errors,
                "warnings": warnings
            }

        except subprocess.TimeoutExpired:
            return {
                "valid": False,
                "errors": ["JavaScript check timeout"],
                "warnings": []
            }
        except Exception as e:
            logger.error(f"Failed to check JavaScript syntax: {e}")
            return {
                "valid": False,
                "errors": [str(e)],
                "warnings": []
            }

    @staticmethod
    async def check_file(
        file_path: str,
        sandbox_path: Path
    ) -> Dict[str, Any]:
        """
        Check syntax for a file based on its extension

        Args:
            file_path: Path to file
            sandbox_path: Path to sandbox directory

        Returns:
            Dictionary with check results
        """
        if file_path.endswith((".ts", ".tsx")):
            return await SandboxSyntaxChecker.check_typescript(file_path, sandbox_path)
        elif file_path.endswith((".js", ".jsx")):
            return await SandboxSyntaxChecker.check_javascript(file_path, sandbox_path)
        else:
            return {
                "valid": True,
                "errors": [],
                "warnings": ["Syntax checking not supported for this file type"]
            }

