"""Structure validation seam for post-install playbook validation."""

from __future__ import annotations

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


class PlaybookStructureValidationMixin:
    def _validate_capability_structure(
        self,
        capability_code: str,
        playbook_codes: Set[str],
        validate_script: Path,
        validation_results: Dict,
    ) -> Dict[str, bool]:
        """
        Validate all playbooks in a capability with a single subprocess.

        Falls back to per-playbook validation when the batched invocation cannot
        be parsed or times out.
        """
        if not playbook_codes:
            return {}

        timeout_seconds = min(120, max(30, len(playbook_codes) * 3))
        process = None

        try:
            process = subprocess.run(
                [
                    sys.executable,
                    str(validate_script),
                    "--capability", capability_code,
                    "--json",
                    "--skip-execution",
                ],
                cwd=str(self.local_core_root),
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                env=self._build_subprocess_env(),
            )
        except subprocess.TimeoutExpired:
            logger.warning(
                "Batched playbook structure validation timed out for %s; "
                "falling back to per-playbook validation",
                capability_code,
            )
            return {}
        except Exception as exc:
            logger.warning(
                "Batched playbook structure validation failed for %s: %s; "
                "falling back to per-playbook validation",
                capability_code,
                exc,
            )
            return {}

        json_output = self._extract_json_output(process.stdout or process.stderr or "")
        if not json_output:
            logger.warning(
                "Batched playbook structure validation returned no parseable JSON "
                "for %s; falling back to per-playbook validation",
                capability_code,
            )
            return {}

        results: Dict[str, bool] = {}
        for validation in json_output.get("validations", []):
            playbook_code = validation.get("playbook_code")
            if not playbook_code or playbook_code not in playbook_codes:
                continue
            if validation.get("passed", False):
                results[playbook_code] = True
                continue
            error_msg = self._format_validation_error(
                validation.get("results", [])
            )
            validation_results["failed"].append({
                "playbook": playbook_code,
                "error": error_msg or "Validation failed",
            })
            logger.error(
                "Playbook %s structure validation failed: %s",
                playbook_code,
                error_msg,
            )
            results[playbook_code] = False
        return results

    def _validate_structure(
        self,
        playbook_code: str,
        capability_code: str,
        validate_script: Path,
        validation_results: Dict
    ) -> bool:
        """
        Validate playbook structure

        Returns:
            True if structure validation passes
        """
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    str(validate_script),
                    "--playbook", playbook_code,
                    "--capability", capability_code,
                    "--json",
                    "--skip-execution"
                ],
                cwd=str(self.local_core_root),
                capture_output=True,
                text=True,
                timeout=5,
                env=self._build_subprocess_env()
            )

            if process.returncode == 0:
                return self._parse_successful_validation(playbook_code, process.stdout, validation_results)
            else:
                return self._parse_failed_validation(playbook_code, process, validation_results)

        except subprocess.TimeoutExpired:
            validation_results["failed"].append({
                "playbook": playbook_code,
                "error": "Structure validation timed out"
            })
            logger.error(f"Playbook {playbook_code} structure validation timed out")
            return False
        except Exception as e:
            validation_results["failed"].append({
                "playbook": playbook_code,
                "error": f"Structure validation error: {str(e)}"
            })
            logger.error(f"Playbook {playbook_code} structure validation error: {e}")
            return False

    def _parse_successful_validation(
        self,
        playbook_code: str,
        output: str,
        validation_results: Dict
    ) -> bool:
        """Parse successful validation output"""
        try:
            json_output = self._extract_json_output(output)

            if json_output:
                validations = json_output.get("validations", [])
                for v in validations:
                    if v.get("playbook_code") == playbook_code:
                        if not v.get("passed", False):
                            error_msg = self._format_validation_error(
                                v.get("results", [])
                            )
                            validation_results["failed"].append({
                                "playbook": playbook_code,
                                "error": error_msg or "Validation failed"
                            })
                            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                            return False
                        else:
                            return True
                return True
            else:
                return True
        except Exception as e:
            logger.debug(f"Playbook {playbook_code} structure validation passed (JSON parse error ignored: {e})")
            return True

    def _parse_failed_validation(
        self,
        playbook_code: str,
        process: subprocess.CompletedProcess,
        validation_results: Dict
    ) -> bool:
        """Parse failed validation output"""
        try:
            output = (process.stderr or process.stdout or "").strip()
            json_output = self._extract_json_output(output)
            if json_output:
                validations = json_output.get("validations", [])
                for v in validations:
                    if v.get("playbook_code") == playbook_code:
                        error_msg = self._format_validation_error(
                            v.get("results", [])
                        )
                        validation_results["failed"].append({
                            "playbook": playbook_code,
                            "error": error_msg or "Validation failed"
                        })
                        logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                        return False

            error_lines = [line for line in output.split('\n') if not line.strip().startswith('[INFO]')]
            error_msg = '\n'.join(error_lines[-10:])
            validation_results["failed"].append({
                "playbook": playbook_code,
                "error": error_msg or "Unknown error"
            })
            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
            return False
        except Exception:
            error_msg = (process.stderr or process.stdout or "Unknown error")[:500]
            validation_results["failed"].append({
                "playbook": playbook_code,
                "error": error_msg
            })
            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
            return False

    def _find_matching_brace(self, text: str, start: int) -> int:
        """Find matching closing brace position"""
        brace_count = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return i + 1
        return start

    def _extract_json_output(self, output: str) -> Optional[Dict]:
        """Extract JSON output from mixed stdout/stderr text."""
        output = output.strip()
        if not output:
            return None

        try:
            return json.loads(output)
        except json.JSONDecodeError:
            pass

        json_start = output.find('{')
        if json_start < 0:
            return None
        json_end = self._find_matching_brace(output, json_start)
        if json_end <= json_start:
            return None
        try:
            return json.loads(output[json_start:json_end])
        except json.JSONDecodeError:
            return None

    def _format_validation_error(self, validation_results: List[Dict]) -> str:
        """Format the first few failed checks from validation output."""
        failed_checks = [
            result for result in validation_results if not result.get("passed", True)
        ]
        return "; ".join(
            f"{result.get('check_name')}: {result.get('message')}"
            for result in failed_checks[:3]
        )
