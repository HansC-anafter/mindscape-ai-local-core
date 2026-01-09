"""
Playbook Validator

验证已安装的 playbooks：
1. 结构验证（通过脚本）
2. 直接工具调用测试（后端模拟，无 LLM）
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Callable

logger = logging.getLogger(__name__)


class PlaybookValidator:
    """验证已安装的 playbooks"""

    def __init__(
        self,
        local_core_root: Path,
        capabilities_dir: Path,
        validate_tools_direct_call_func: Optional[Callable] = None
    ):
        """
        初始化 Playbook 验证器

        Args:
            local_core_root: Local-core 项目根目录
            capabilities_dir: 能力目录
            validate_tools_direct_call_func: 直接调用工具验证函数
        """
        self.local_core_root = local_core_root
        self.capabilities_dir = capabilities_dir
        self._validate_tools_direct_call = validate_tools_direct_call_func

    def validate_installed_playbooks(
        self,
        capability_code: str,
        manifest: Dict,
        result
    ):
        """
        验证已安装的 playbooks

        Args:
            capability_code: 能力代码
            manifest: 解析后的 manifest 字典
            result: InstallResult 对象
        """
        playbooks_config = manifest.get('playbooks', [])
        if not playbooks_config:
            return

        validation_results = {
            "validated": [],
            "failed": [],
            "skipped": []
        }

        # Check if validation script exists
        validate_script = self.local_core_root / "scripts" / "validate_playbooks.py"
        if not validate_script.exists():
            logger.warning("validate_playbooks.py not found, skipping playbook validation")
            result.add_warning("Playbook validation skipped: script not found")
            return

        for pb_config in playbooks_config:
            playbook_code = pb_config.get('code')
            if not playbook_code:
                continue

            # 1. Structure validation (via script)
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
                    validation_results
                )
            elif structure_valid:
                # Structure valid but no tool validation function provided
                validation_results["validated"].append(playbook_code)
                logger.info(f"Playbook {playbook_code} structure validated (tool call test skipped)")

        # Add validation results to result
        result.playbook_validation = validation_results

        # Process validation results and add to result
        self._process_validation_results(validation_results, result)

    def _validate_structure(
        self,
        playbook_code: str,
        capability_code: str,
        validate_script: Path,
        validation_results: Dict
    ) -> bool:
        """
        验证 playbook 结构

        Returns:
            True 如果结构验证通过
        """
        try:
            process = subprocess.run(
                [
                    sys.executable,
                    str(validate_script),
                    "--playbook", playbook_code,
                    "--capability", capability_code,
                    "--json",
                    "--skip-execution"  # Skip execution test, only structure validation
                ],
                cwd=str(self.local_core_root),
                capture_output=True,
                text=True,
                timeout=5,  # Structure validation should complete in 1 second, 5 second buffer
                env={
                    **dict(os.environ),
                    "LLM_MOCK": "false",  # Skip execution test, no mock needed
                    "BASE_URL": "http://localhost:8200",
                    "PYTHONPATH": f"{self.local_core_root}:{self.local_core_root / 'backend'}",
                    "CAPABILITIES_PATH": str(self.capabilities_dir)
                }
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
        """解析成功的验证输出"""
        try:
            output = output.strip()
            json_output = None

            # Try to parse JSON from the beginning
            try:
                json_output = json.loads(output)
            except json.JSONDecodeError:
                # If parsing from beginning fails, try to find the first complete JSON object
                json_start = output.find('{')
                if json_start >= 0:
                    json_end = self._find_matching_brace(output, json_start)
                    if json_end > json_start:
                        json_output = json.loads(output[json_start:json_end])

            if json_output:
                validations = json_output.get("validations", [])
                for v in validations:
                    if v.get("playbook_code") == playbook_code:
                        if not v.get("passed", False):
                            # Structure validation failed
                            failed_checks = [r for r in v.get("results", []) if not r.get("passed", True)]
                            error_msg = "; ".join([f"{r.get('check_name')}: {r.get('message')}" for r in failed_checks[:3]])
                            validation_results["failed"].append({
                                "playbook": playbook_code,
                                "error": error_msg or "Validation failed"
                            })
                            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                            return False
                        else:
                            return True
                # Playbook not found, treat as passed (may be other issue)
                return True
            else:
                # No JSON output, treat as passed
                return True
        except Exception as e:
            # JSON parsing failed but returncode is 0, treat as passed
            logger.debug(f"Playbook {playbook_code} structure validation passed (JSON parse error ignored: {e})")
            return True

    def _parse_failed_validation(
        self,
        playbook_code: str,
        process: subprocess.CompletedProcess,
        validation_results: Dict
    ) -> bool:
        """解析失败的验证输出"""
        try:
            output = (process.stderr or process.stdout or "").strip()
            # Find JSON part
            json_start = output.rfind('{')
            if json_start >= 0:
                json_end = self._find_matching_brace(output, json_start)
                if json_end > json_start:
                    json_output = json.loads(output[json_start:json_end])
                    validations = json_output.get("validations", [])
                    for v in validations:
                        if v.get("playbook_code") == playbook_code:
                            failed_checks = [r for r in v.get("results", []) if not r.get("passed", True)]
                            error_msg = "; ".join([f"{r.get('check_name')}: {r.get('message')}" for r in failed_checks[:3]])
                            validation_results["failed"].append({
                                "playbook": playbook_code,
                                "error": error_msg or "Validation failed"
                            })
                            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                            return False

            # Not found or no JSON, use original error message
            error_lines = [line for line in output.split('\n') if not line.strip().startswith('[INFO]')]
            error_msg = '\n'.join(error_lines[-10:])  # Only take last 10 lines
            validation_results["failed"].append({
                "playbook": playbook_code,
                "error": error_msg or "Unknown error"
            })
            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
            return False
        except Exception as e:
            # JSON parsing failed, use original error message
            error_msg = (process.stderr or process.stdout or "Unknown error")[:500]
            validation_results["failed"].append({
                "playbook": playbook_code,
                "error": error_msg
            })
            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
            return False

    def _find_matching_brace(self, text: str, start: int) -> int:
        """找到匹配的右大括号位置"""
        brace_count = 0
        for i in range(start, len(text)):
            if text[i] == '{':
                brace_count += 1
            elif text[i] == '}':
                brace_count -= 1
                if brace_count == 0:
                    return i + 1
        return start  # Not found

    def _validate_tool_calls(
        self,
        playbook_code: str,
        capability_code: str,
        validation_results: Dict
    ):
        """验证工具调用"""
        try:
            tool_test_errors, tool_test_warnings = self._validate_tools_direct_call(playbook_code, capability_code)

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
        """将工具错误分类为可选依赖错误和关键错误"""
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
        """格式化关键错误消息"""
        if len(critical_errors) == 1:
            return critical_errors[0]
        else:
            error_msg = f"{len(critical_errors)} tool validation errors: " + "; ".join(critical_errors[:3])
            if len(critical_errors) > 3:
                error_msg += f" (and {len(critical_errors) - 3} more)"
            return error_msg

    def _format_optional_dep_warning(self, optional_dep_errors: List[str]) -> str:
        """格式化可选依赖警告消息"""
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
        """处理验证结果并添加到 result"""
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

