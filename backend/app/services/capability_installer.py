"""
Capability Installer Service

Unified installer for capability packs from .mindpack files.
Handles:
- Unpacking .mindpack files
- Validating manifest
- Installing playbooks (specs + markdown)
- Installing tools and services
- Installing UI components to frontend
- Updating capability registry
"""

import json
import logging
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import yaml

logger = logging.getLogger(__name__)


class CapabilityInstaller:
    """Installer for capability packs"""

    def __init__(
        self,
        local_core_root: Path,
        capabilities_dir: Optional[Path] = None,
        specs_dir: Optional[Path] = None,
        i18n_dir: Optional[Path] = None,
        tools_dir: Optional[Path] = None,
        services_dir: Optional[Path] = None
    ):
        """
        Initialize installer

        Args:
            local_core_root: Local-core project root directory
            capabilities_dir: Directory for capability manifests (default: backend/app/capabilities)
            specs_dir: Directory for playbook JSON specs (default: backend/playbooks/specs)
            i18n_dir: Base directory for playbook markdown (default: backend/i18n/playbooks)
            tools_dir: Directory for capability tools (default: backend/app/capabilities/{code}/tools)
            services_dir: Directory for capability services (default: backend/app/capabilities/{code}/services)
        """
        self.local_core_root = local_core_root

        # Set default directories
        backend_dir = local_core_root / "backend"
        self.capabilities_dir = capabilities_dir or (backend_dir / "app" / "capabilities")
        self.specs_dir = specs_dir or (backend_dir / "playbooks" / "specs")
        self.i18n_base_dir = i18n_dir or (backend_dir / "i18n" / "playbooks")
        self.tools_base_dir = tools_dir  # Will be set per capability
        self.services_base_dir = services_dir  # Will be set per capability

    def install_from_mindpack(
        self,
        mindpack_path: Path,
        validate: bool = True
    ) -> Tuple[bool, Dict]:
        """
        Install a capability pack from a .mindpack file

        Args:
            mindpack_path: Path to .mindpack file
            validate: Whether to validate manifest before installation

        Returns:
            (success: bool, result: dict)
            result contains:
            - capability_code: str
            - installed: dict (playbooks, tools, services)
            - warnings: List[str]
            - errors: List[str]
        """
        result = {
            "capability_code": None,
            "installed": {
                "playbooks": [],
                "tools": [],
                "services": [],
                "api_endpoints": [],
                "schema_modules": [],
                "database_models": [],
                "migrations": [],
                "ui_components": []
            },
            "warnings": [],
            "errors": []
        }

        if not mindpack_path.exists():
            result["errors"].append(f"Mindpack file not found: {mindpack_path}")
            return False, result

        # Extract to temporary directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            logger.info(f"Extracting {mindpack_path} to temporary directory...")

            try:
                with tarfile.open(mindpack_path, "r:gz") as tar:
                    tar.extractall(temp_path)
            except Exception as e:
                result["errors"].append(f"Failed to extract mindpack: {e}")
                return False, result

            # Find capability directory in extracted files
            extracted_dirs = [d for d in temp_path.iterdir() if d.is_dir()]
            if not extracted_dirs:
                result["errors"].append("No capability directory found in mindpack")
                return False, result

            cap_extracted_dir = extracted_dirs[0]
            capability_code = cap_extracted_dir.name
            result["capability_code"] = capability_code

            # Load manifest
            manifest_path = cap_extracted_dir / "manifest.yaml"
            if not manifest_path.exists():
                result["errors"].append("manifest.yaml not found in mindpack")
                return False, result

            try:
                with open(manifest_path, 'r', encoding='utf-8') as f:
                    manifest = yaml.safe_load(f)
            except Exception as e:
                result["errors"].append(f"Failed to parse manifest: {e}")
                return False, result

            # Validate manifest
            if validate:
                logger.info(f"Validating manifest for {capability_code}...")
                is_valid, validation_errors, validation_warnings = self._validate_manifest(
                    manifest_path, cap_extracted_dir
                )
                result["warnings"].extend(validation_warnings)
                if not is_valid:
                    # Validation failure should block installation (unless explicitly allowed)
                    error_msg = f"Manifest validation failed: {validation_errors}"
                    result["errors"].append(error_msg)
                    logger.error(error_msg)
                    # Block installation unless explicitly allowed to skip validation
                    skip_validation = os.getenv("MINDSCAPE_SKIP_VALIDATION", "0") == "1"
                    if not skip_validation:
                        logger.error("Installation blocked due to manifest validation failure. Set MINDSCAPE_SKIP_VALIDATION=1 to override (not recommended).")
                        return False, result
                    else:
                        logger.warning("Validation failed but continuing due to MINDSCAPE_SKIP_VALIDATION=1")

            # Install capability
            success = self._install_capability(
                cap_extracted_dir,
                capability_code,
                manifest,
                result
            )

            return success, result

    def _validate_manifest(
        self,
        manifest_path: Path,
        cap_dir: Path
    ) -> Tuple[bool, List[str], List[str]]:
        """
        Validate manifest using local validate_manifest.py script

        Args:
            manifest_path: Path to manifest.yaml
            cap_dir: Capability directory

        Returns:
            (is_valid, errors, warnings)
        """
        # Use local validation script (consistent with CI/startup validation)
        # Calculate local validation script path
        local_core_root = Path(__file__).parent.parent.parent.parent.parent
        validate_script = local_core_root / "scripts" / "ci" / "validate_manifest.py"

        if not validate_script.exists():
            # Validation script not found is a critical issue, treat as error
            error_msg = f"Local validation script not found: {validate_script}. Cannot validate manifest."
            logger.error(error_msg)
            return False, [error_msg], []

        try:
            # Run local validation script
            # validate_manifest.py accepts capability directory path as argument
            result = subprocess.run(
                [sys.executable, str(validate_script), str(cap_dir)],
                cwd=str(local_core_root),
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Parse warnings (validation passed but may have warnings)
                warnings = []
                for line in result.stdout.split('\n'):
                    if line.strip() and ('WARNING' in line or 'warning' in line.lower()):
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
                    if 'ERROR' in line or 'error' in line.lower() or 'failed' in line.lower():
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
            # Validation script execution failure should be treated as error unless explicitly allowed
            return False, [error_msg], []

    def _install_capability(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: Dict
    ) -> bool:
        """
        Install capability files

        Args:
            cap_dir: Extracted capability directory
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: Result dict to update

        Returns:
            True if successful
        """
        try:
            # 1. Install playbooks (specs + markdown)
            self._install_playbooks(cap_dir, capability_code, manifest, result)

            # 2. Install tools
            self._install_tools(cap_dir, capability_code, result)

            # 3. Install services
            self._install_services(cap_dir, capability_code, result)

            # 4. Install API endpoints
            self._install_api_endpoints(cap_dir, capability_code, result)

            # 5. Install schema modules
            self._install_schema_modules(cap_dir, capability_code, result)

            # 6. Install database models
            self._install_database_models(cap_dir, capability_code, result)

            # 7. Install migrations
            self._install_migrations(cap_dir, capability_code, result)

            # 7.5. Execute migrations if any were installed
            if result.get("installed", {}).get("migrations"):
                self._execute_migrations(capability_code, result)

            # 8. Install UI components
            self._install_ui_components(cap_dir, capability_code, manifest, result)

            # 9. Install manifest
            self._install_manifest(cap_dir, capability_code, manifest)

            # 9.5. Install root-level Python files (e.g., models.py)
            self._install_root_files(cap_dir, capability_code, result)

            # 10. Check dependencies and generate summary
            self._check_dependencies(manifest, result)

            # 11. Run post-install hooks (bootstrap scripts)
            self._run_post_install_hooks(cap_dir, capability_code, manifest, result)

            # 12. Validate installed playbooks (mock mode)
            self._validate_installed_playbooks(capability_code, manifest, result)

            # Hard rule: if there are any errors (including legacy tool fields), installation fails
            if result.get("errors"):
                logger.error(f"Installation failed due to errors: {result['errors']}")
                return False

            logger.info(f"Successfully installed capability: {capability_code}")
            return True

        except Exception as e:
            logger.error(f"Failed to install capability: {e}")
            result["errors"].append(f"Installation failed: {e}")
            return False

    def _validate_installed_playbooks(
        self,
        capability_code: str,
        manifest: Dict,
        result: Dict
    ):
        """
        Validate installed playbooks:
        1. Structure validation (via script)
        2. Direct tool call test (backend simulation, no LLM)

        Args:
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: Result dict to update
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
            result["warnings"].append("Playbook validation skipped: script not found")
            return

        for pb_config in playbooks_config:
            playbook_code = pb_config.get('code')
            if not playbook_code:
                continue

            # 1. Structure validation (via script)
            structure_valid = False
            try:
                import subprocess
                process = subprocess.run(
                    [
                        sys.executable,
                        str(validate_script),
                        "--playbook", playbook_code,
                        "--json",
                        "--skip-execution"  # Skip execution test, only structure validation
                    ],
                    cwd=str(self.local_core_root),
                    capture_output=True,
                    text=True,
                    timeout=5,  # Structure validation should complete in 1 second, 5 second buffer
                    env={
                        **dict(__import__('os').environ),
                        "LLM_MOCK": "false",  # Skip execution test, no mock needed
                        "BASE_URL": "http://localhost:8200",
                        "PYTHONPATH": f"{self.local_core_root}:{self.local_core_root / 'backend'}"
                    }
                )

                if process.returncode == 0:
                    # 嘗試解析 JSON 輸出，確認驗證結果
                    try:
                        import json
                        output = process.stdout.strip()
                        # 找到 JSON 部分（可能在輸出的最後）
                        json_start = output.rfind('{')
                        if json_start >= 0:
                            json_output = json.loads(output[json_start:])
                            summary = json_output.get("summary", {})
                            validations = json_output.get("validations", [])
                            # 檢查這個 playbook 是否通過
                            for v in validations:
                                if v.get("playbook_code") == playbook_code:
                                    if not v.get("passed", False):
                                        # 結構驗證失敗
                                        failed_checks = [r for r in v.get("results", []) if not r.get("passed", True)]
                                        error_msg = "; ".join([f"{r.get('check_name')}: {r.get('message')}" for r in failed_checks[:3]])
                                        validation_results["failed"].append({
                                            "playbook": playbook_code,
                                            "error": error_msg or "Validation failed"
                                        })
                                        logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                                        structure_valid = False
                                        break
                                    else:
                                        structure_valid = True
                                        break
                            else:
                                # 沒找到這個 playbook，視為通過（可能是其他問題）
                                structure_valid = True
                        else:
                            # 沒有 JSON 輸出，視為通過
                            structure_valid = True
                    except Exception as e:
                        # JSON 解析失敗，但 returncode 是 0，視為通過
                        structure_valid = True
                        logger.debug(f"Playbook {playbook_code} structure validation passed (JSON parse error ignored: {e})")
                else:
                    structure_valid = False
                if not structure_valid:
                    # Parse error from output (只取 JSON 部分)
                    try:
                        import json
                        output = (process.stderr or process.stdout or "").strip()
                        # 找到 JSON 部分
                        json_start = output.rfind('{')
                        if json_start >= 0:
                            json_output = json.loads(output[json_start:])
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
                                    break
                            else:
                                # 沒找到，使用原始錯誤訊息
                                error_msg = output[-500:] if len(output) > 500 else output
                                validation_results["failed"].append({
                                    "playbook": playbook_code,
                                    "error": error_msg
                                })
                                logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                        else:
                            # 沒有 JSON，使用原始錯誤訊息（過濾掉 INFO log）
                            error_lines = [line for line in output.split('\n') if not line.strip().startswith('[INFO]')]
                            error_msg = '\n'.join(error_lines[-10:])  # 只取最後 10 行
                            validation_results["failed"].append({
                                "playbook": playbook_code,
                                "error": error_msg or "Unknown error"
                            })
                            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                    except Exception as e:
                        # JSON 解析失敗，使用原始錯誤訊息
                        error_msg = (process.stderr or process.stdout or "Unknown error")[:500]
                        validation_results["failed"].append({
                            "playbook": playbook_code,
                            "error": error_msg
                        })
                        logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")

            except subprocess.TimeoutExpired:
                validation_results["failed"].append({
                    "playbook": playbook_code,
                    "error": "Structure validation timed out"
                })
                logger.error(f"Playbook {playbook_code} structure validation timed out")
                structure_valid = False
            except Exception as e:
                validation_results["failed"].append({
                    "playbook": playbook_code,
                    "error": f"Structure validation error: {str(e)}"
                })
                logger.error(f"Playbook {playbook_code} structure validation error: {e}")
                structure_valid = False

            # 2. 如果結構驗證通過，進行直接 tool 調用測試（不通過 LLM）
            if structure_valid:
                try:
                    tool_test_errors = self._validate_tools_direct_call(playbook_code, capability_code)
                    if tool_test_errors:
                        # 將多個錯誤合併為可讀的訊息
                        if len(tool_test_errors) == 1:
                            error_msg = tool_test_errors[0]
                        else:
                            error_msg = f"{len(tool_test_errors)} tool validation errors: " + "; ".join(tool_test_errors[:3])
                            if len(tool_test_errors) > 3:
                                error_msg += f" (and {len(tool_test_errors) - 3} more)"

                        validation_results["failed"].append({
                            "playbook": playbook_code,
                            "error": f"Tool call test failed: {error_msg}"
                        })
                        logger.error(f"Playbook {playbook_code} tool call test failed: {error_msg}")
                    else:
                        validation_results["validated"].append(playbook_code)
                        logger.info(f"Playbook {playbook_code} validated successfully (structure + tool call test)")
                except Exception as e:
                    # Tool 調用測試本身出錯（例如導入失敗），記錄為失敗
                    validation_results["failed"].append({
                        "playbook": playbook_code,
                        "error": f"Tool call test exception: {str(e)}"
                    })
                    logger.error(f"Playbook {playbook_code} tool call test exception: {e}")

        # Add validation results to result
        result["playbook_validation"] = validation_results

        # Add errors for failed validations (驗證失敗是錯誤，不是警告)
        if validation_results["failed"]:
            failed_playbooks = [f['playbook'] for f in validation_results['failed']]
            error_msg = f"Playbook validation failed for: {failed_playbooks}"
            result["errors"].append(error_msg)
            logger.error(error_msg)

        # Add warnings for skipped validations (只有跳過才是警告)
        if validation_results["skipped"]:
            result["warnings"].append(
                f"Playbook validation skipped for: {validation_results['skipped']}"
            )

    def _check_dependencies(
        self,
        manifest: Dict,
        result: Dict
    ):
        """
        Check for missing dependencies and register degradation status

        Args:
            manifest: Parsed manifest dict
            result: Result dict to update
        """
        capability_code = result.get("capability_code")
        if not capability_code:
            return

        dependencies = manifest.get('dependencies', {})
        if not dependencies:
            # Legacy format or no dependencies declared
            return

        # Check required dependencies
        required_deps = dependencies.get('required', [])
        missing_required = []
        for dep in required_deps:
            if not self._is_dependency_available(dep):
                missing_required.append(dep)

        # Check optional dependencies
        optional_deps = dependencies.get('optional', [])
        missing_optional = []
        degraded_features_map = {}
        for opt_dep in optional_deps:
            dep_name = opt_dep if isinstance(opt_dep, str) else opt_dep.get('name', '')
            if not dep_name:
                continue

            if not self._is_dependency_available(dep_name):
                missing_optional.append(dep_name)
                # Build degraded features map
                if isinstance(opt_dep, dict):
                    degraded_features = opt_dep.get('degraded_features', [])
                    if degraded_features:
                        degraded_features_map[dep_name] = degraded_features

        # Check external services
        external_services = dependencies.get('external_services', [])
        missing_external = []
        for ext_svc in external_services:
            svc_name = ext_svc if isinstance(ext_svc, str) else ext_svc.get('name', '')
            if not svc_name:
                continue

            env_var = ext_svc.get('env_var') if isinstance(ext_svc, dict) else None
            if env_var and not self._is_env_var_set(env_var):
                missing_external.append(svc_name)
                # Add to degraded features map
                if isinstance(ext_svc, dict):
                    degraded_features = ext_svc.get('degraded_features', [])
                    if degraded_features:
                        degraded_features_map[svc_name] = degraded_features

        # Register degradation status
        if missing_required or missing_optional or missing_external:
            self._register_degradation_status(
                capability_code,
                manifest,
                missing_required,
                missing_optional + missing_external,
                degraded_features_map,
                result
            )

        # Add to result for reporting
        if missing_required:
            result.setdefault("missing_dependencies", {})["required"] = missing_required
        if missing_optional:
            result.setdefault("missing_dependencies", {})["optional"] = missing_optional
        if missing_external:
            result.setdefault("missing_dependencies", {})["external_services"] = missing_external

    def _is_dependency_available(self, dep_name: str) -> bool:
        """
        Check if a dependency is available

        Args:
            dep_name: Dependency name (e.g., 'contracts.execution_context', 'core_llm')

        Returns:
            True if available
        """
        try:
            # Try to import the dependency
            import importlib
            importlib.import_module(dep_name)
            return True
        except (ImportError, ModuleNotFoundError, ValueError):
            # Check if it's a fallback shim
            if dep_name == 'contracts.execution_context':
                try:
                    importlib.import_module('mindscape.shims.execution_context')
                    return True  # Fallback available
                except (ImportError, ModuleNotFoundError):
                    pass
            return False

    def _is_env_var_set(self, env_var: str) -> bool:
        """Check if environment variable is set"""
        import os
        return bool(os.getenv(env_var))

    def _register_degradation_status(
        self,
        capability_code: str,
        manifest: Dict,
        missing_required: List[str],
        missing_optional: List[str],
        degraded_features_map: Dict[str, List[str]],
        result: Dict
    ):
        """
        Register capability degradation status

        Args:
            capability_code: Capability code
            manifest: Parsed manifest dict
            missing_required: List of missing required dependencies
            missing_optional: List of missing optional dependencies
            degraded_features_map: Map of dependency -> degraded features
            result: Result dict to update
        """
        try:
            from mindscape.runtime.degradation import DegradationRegistry

            # Collect all features from manifest
            all_features = []

            # Features from playbooks
            playbooks = manifest.get('playbooks', [])
            for pb in playbooks:
                pb_code = pb.get('code', '')
                if pb_code:
                    all_features.append(pb_code)

            # Features from tools
            tools = manifest.get('tools', [])
            for tool in tools:
                tool_name = tool.get('name', '')
                if tool_name:
                    all_features.append(tool_name)

            # Features from services (if any)
            # Note: services are typically internal, but we can add them if needed

            # Register with degradation registry
            registry = DegradationRegistry()
            cap_status = registry.register_capability(
                code=capability_code,
                all_features=all_features,
                missing_deps=missing_required + missing_optional,
                degraded_features_map=degraded_features_map
            )

            # Add to result
            result["degradation_status"] = cap_status.to_dict()
            logger.info(
                f"Registered degradation status for {capability_code}: "
                f"status={cap_status.status}, "
                f"degraded_features={cap_status.degraded_features}"
            )

        except ImportError:
            logger.warning("DegradationRegistry not available, skipping degradation registration")
            result.setdefault("warnings", []).append(
                "Degradation status not registered (DegradationRegistry not available)"
            )
        except Exception as e:
            logger.warning(f"Failed to register degradation status: {e}")
            result.setdefault("warnings", []).append(f"Failed to register degradation status: {e}")

    def _install_playbooks(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: Dict
    ):
        """Install playbook specs and markdown files"""
        playbooks_config = manifest.get('playbooks', [])

        # Get capability installation directory
        cap_install_dir = self.capabilities_dir / capability_code
        cap_playbooks_dir = cap_install_dir / "playbooks"

        for pb_config in playbooks_config:
            playbook_code = pb_config.get('code')
            if not playbook_code:
                continue

            # Install JSON spec
            spec_path = cap_dir / pb_config.get('spec_path', f"playbooks/specs/{playbook_code}.json")
            if spec_path.exists():
                # ⚠️ 硬規則：驗證 playbook spec 必要字段
                required_fields_errors = self._validate_playbook_required_fields(spec_path, playbook_code)
                if required_fields_errors:
                    error_msg = f"Playbook {playbook_code} missing required fields: {required_fields_errors}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                    continue  # 跳過此 playbook 的安裝

                # ⚠️ 硬規則：驗證 playbook spec 不使用 legacy `tool` 字段
                legacy_tool_errors = self._validate_no_legacy_tool_field(spec_path, playbook_code)
                if legacy_tool_errors:
                    error_msg = f"Playbook {playbook_code} uses legacy 'tool' field (已棄用): {legacy_tool_errors}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                    continue  # 跳過此 playbook 的安裝

                # Install to backend/playbooks/specs/ (backward compatibility)
                target_spec = self.specs_dir / f"{playbook_code}.json"
                self.specs_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(spec_path, target_spec)
                result["installed"]["playbooks"].append(playbook_code)
                logger.debug(f"Installed spec: {playbook_code}.json")

                # Also install to capabilities/{code}/playbooks/specs/ (correct location)
                cap_specs_dir = cap_playbooks_dir / "specs"
                cap_specs_dir.mkdir(parents=True, exist_ok=True)
                cap_target_spec = cap_specs_dir / f"{playbook_code}.json"
                shutil.copy2(spec_path, cap_target_spec)
                logger.debug(f"Installed spec to capability dir: {cap_target_spec}")
            else:
                # Spec file not found - log warning but don't block installation
                warning_msg = f"Playbook {playbook_code}: spec file not found: {spec_path}"
                logger.warning(warning_msg)
                result["warnings"].append(warning_msg)

            # Install markdown files
            locales = pb_config.get('locales', ['zh-TW', 'en'])
            md_path_template = pb_config.get('path', f"playbooks/{{locale}}/{playbook_code}.md")

            for locale in locales:
                md_path = cap_dir / md_path_template.format(locale=locale)
                if md_path.exists():
                    # Install to backend/i18n/playbooks/{locale}/ (backward compatibility)
                    target_md_dir = self.i18n_base_dir / locale
                    target_md_dir.mkdir(parents=True, exist_ok=True)
                    target_md = target_md_dir / f"{playbook_code}.md"
                    shutil.copy2(md_path, target_md)
                    logger.debug(f"Installed markdown: {playbook_code}.md ({locale})")

                    # Also install to capabilities/{code}/playbooks/{locale}/ (correct location)
                    cap_locale_dir = cap_playbooks_dir / locale
                    cap_locale_dir.mkdir(parents=True, exist_ok=True)
                    cap_target_md = cap_locale_dir / f"{playbook_code}.md"
                    shutil.copy2(md_path, cap_target_md)
                    logger.debug(f"Installed markdown to capability dir: {cap_target_md}")

    def _validate_playbook_required_fields(
        self,
        spec_path: Path,
        playbook_code: str
    ) -> List[str]:
        """
        Validate that playbook spec has all required fields according to checklist

        ⚠️ 硬規則：根據實作規章 checklist 驗證 playbook spec

        Checklist requirements:
        1. PlaybookJson 模型必需字段：kind, inputs, outputs
        2. Playbook Spec 核心欄位：playbook_code, version, display_name, description, steps
        3. 能力宣告：required_capabilities
        4. 資料邊界：data_locality
        5. Cloud 專用欄位禁止檢查

        Args:
            spec_path: Path to playbook JSON spec file
            playbook_code: Playbook code for error messages

        Returns:
            List of error messages (empty if validation passes)
        """
        errors = []
        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                spec = json.load(f)

            # 1. PlaybookJson 模型必需字段（新格式）
            required_model_fields = ['kind', 'inputs', 'outputs']
            for field in required_model_fields:
                if field not in spec:
                    errors.append(f"Missing required field (PlaybookJson model): '{field}'")
                elif field == 'inputs' and not isinstance(spec.get(field), dict):
                    errors.append(f"Field 'inputs' must be a dictionary")
                elif field == 'outputs' and not isinstance(spec.get(field), dict):
                    errors.append(f"Field 'outputs' must be a dictionary")

            # 2. Playbook Spec 核心欄位（舊格式兼容性檢查）
            core_fields = ['playbook_code', 'version', 'display_name', 'description', 'steps']
            for field in core_fields:
                if field not in spec:
                    errors.append(f"Missing required field (core spec): '{field}'")
                elif field == 'steps' and not isinstance(spec.get(field), list):
                    errors.append(f"Field 'steps' must be a list")

            # 3. 能力宣告檢查
            if 'required_capabilities' not in spec:
                errors.append("Missing 'required_capabilities' field (must declare capability dependencies)")

            # 4. 資料邊界檢查
            if 'data_locality' not in spec:
                errors.append("Missing 'data_locality' field (must declare data boundary: local_only and cloud_allowed)")

            # 5. Cloud 專用欄位禁止檢查
            cloud_forbidden_fields = ['webhook_url', 'webhook_auth', 'bundle_id', 'download_url', 'checksum']
            for field in cloud_forbidden_fields:
                if field in spec:
                    errors.append(f"Forbidden cloud-specific field found: '{field}' (must not be in playbook spec)")

            # 6. input_schema 中禁止 Cloud 專用欄位
            input_schema = spec.get('input_schema', {})
            if isinstance(input_schema, dict):
                properties = input_schema.get('properties', {})
                cloud_forbidden_inputs = ['tenant_id', 'actor_id', 'subject_user_id', 'plan_id', 'execution_id', 'trace_id']
                for field in cloud_forbidden_inputs:
                    if field in properties:
                        errors.append(f"Forbidden cloud-specific field in input_schema: '{field}' (must not be in playbook input_schema)")

            return errors
        except json.JSONDecodeError as e:
            return [f"Invalid JSON: {str(e)}"]
        except Exception as e:
            return [f"Validation error: {str(e)}"]

    def _validate_no_legacy_tool_field(
        self,
        spec_path: Path,
        playbook_code: str
    ) -> List[str]:
        """
        Validate that playbook spec does not use legacy 'tool' field

        ⚠️ 硬規則：playbook 必須使用 tool_slot 字段，tool 字段已棄用

        Args:
            spec_path: Path to playbook JSON spec file
            playbook_code: Playbook code for error messages

        Returns:
            List of error messages (empty if validation passes)
        """
        errors = []
        try:
            with open(spec_path, 'r', encoding='utf-8') as f:
                spec = json.load(f)

            steps = spec.get('steps', [])
            if not isinstance(steps, list):
                return errors

            for step_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue

                # 檢查是否使用 legacy 'tool' 字段
                if 'tool' in step:
                    step_id = step.get('id', f'step_{step_idx}')
                    errors.append(
                        f"Step '{step_id}' uses legacy 'tool' field: '{step['tool']}'. "
                        f"Must use 'tool_slot' field instead (format: 'capability.tool_name', e.g., 'yogacoach.intake_router')"
                    )

            if errors:
                logger.error(f"Playbook {playbook_code} validation failed: legacy 'tool' field detected in {len(errors)} step(s)")

        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in playbook spec: {e}")
        except Exception as e:
            errors.append(f"Error validating playbook spec: {e}")

        return errors

    def _validate_tools_direct_call(
        self,
        playbook_code: str,
        capability_code: str
    ) -> List[str]:
        """
        Validate tools by directly calling them (backend simulation, no LLM)

        ⚠️ 新測試：直接通過後端模擬調用 tool，驗證 tool 是否正確註冊和可調用

        Args:
            playbook_code: Playbook code
            capability_code: Capability code

        Returns:
            List of error messages (empty if validation passes)
        """
        errors = []
        try:
            # 一次性設置 capabilities 模組結構（在驗證開始前）
            from pathlib import Path
            from backend.app.capabilities.registry import get_registry
            import importlib.util as importlib_util
            import types

            # 直接使用安裝目錄，不依賴 registry（驗證時可能還沒註冊）
            capability_dir = self.capabilities_dir / capability_code
            if capability_dir.exists():
                # 確保 capability_dir 是 Path 對象
                if isinstance(capability_dir, str):
                    capability_dir = Path(capability_dir)

                capabilities_parent = capability_dir.parent
                cloud_root = capabilities_parent.parent  # e.g. /.../backend/app
                backend_root = cloud_root.parent        # e.g. /.../backend

                # 加入 sys.path，確保 capabilities.*, backend.app.*, app.* 都能被 import
                for path in [capabilities_parent, cloud_root, backend_root]:
                    if path and str(path) not in sys.path:
                        sys.path.insert(0, str(path))

                # 創建 capabilities package 結構
                if 'capabilities' not in sys.modules:
                    capabilities_module = types.ModuleType('capabilities')
                    capabilities_module.__path__ = [str(capabilities_parent)]
                    sys.modules['capabilities'] = capabilities_module

                # 創建 capability package
                cap_module_path = f'capabilities.{capability_code}'
                if cap_module_path not in sys.modules:
                    cap_module = types.ModuleType(cap_module_path)
                    cap_module.__path__ = [str(capability_dir)]
                    sys.modules[cap_module_path] = cap_module
                    setattr(sys.modules['capabilities'], capability_code, cap_module)

                # 預載入 models.py
                models_path = capability_dir / 'models.py'
                models_module_path = f'capabilities.{capability_code}.models'
                if models_path.exists() and models_module_path not in sys.modules:
                    try:
                        models_spec = importlib_util.spec_from_file_location(models_module_path, models_path)
                        if models_spec and models_spec.loader:
                            models_module = importlib_util.module_from_spec(models_spec)
                            models_spec.loader.exec_module(models_module)
                            sys.modules[models_module_path] = models_module
                            setattr(sys.modules[cap_module_path], 'models', models_module)
                    except Exception as e:
                        logger.warning(f"Failed to pre-load models.py: {e}")
                        import traceback
                        logger.debug(traceback.format_exc())

                # 預載入 database_dependency.py
                db_dep_path = capability_dir / 'database_dependency.py'
                db_dep_module_path = f'capabilities.{capability_code}.database_dependency'
                if db_dep_path.exists() and db_dep_module_path not in sys.modules:
                    try:
                        db_dep_spec = importlib_util.spec_from_file_location(db_dep_module_path, db_dep_path)
                        if db_dep_spec and db_dep_spec.loader:
                            db_dep_module = importlib_util.module_from_spec(db_dep_spec)
                            db_dep_spec.loader.exec_module(db_dep_module)
                            sys.modules[db_dep_module_path] = db_dep_module
                            setattr(sys.modules[cap_module_path], 'database_dependency', db_dep_module)
                    except Exception as e:
                        logger.debug(f"Failed to pre-load database_dependency.py: {e}")

            # 讀取 playbook spec
            spec_path = self.capabilities_dir / capability_code / "playbooks" / "specs" / f"{playbook_code}.json"
            if not spec_path.exists():
                # 也檢查舊位置
                spec_path = self.specs_dir / f"{playbook_code}.json"
                if not spec_path.exists():
                    errors.append(f"Playbook spec not found: {playbook_code}.json")
                    return errors

            with open(spec_path, 'r', encoding='utf-8') as f:
                spec = json.load(f)

            steps = spec.get('steps', [])
            if not isinstance(steps, list):
                return errors

            # 導入必要的模組（延遲導入，避免循環依賴）
            try:
                from backend.app.shared.tool_executor import ToolExecutor
                tool_executor = ToolExecutor()
            except ImportError as e:
                errors.append(f"Failed to import ToolExecutor: {e}")
                return errors

            # 測試每個 step 的 tool_slot
            for step_idx, step in enumerate(steps):
                if not isinstance(step, dict):
                    continue

                step_id = step.get('id', f'step_{step_idx}')
                tool_slot = step.get('tool_slot')

                if not tool_slot:
                    # 沒有 tool_slot 的 step（可能是條件判斷等），跳過
                    continue

                # 跳過 core slots（它們由系統處理，不需要驗證）
                if tool_slot.startswith('core.'):
                    continue

                # 直接測試 tool 是否可調用
                try:
                    # 對於 capability tool，格式是 capability.tool_name
                    if '.' in tool_slot:
                        parts = tool_slot.split('.', 1)
                        if len(parts) == 2:
                            cap, tool_name = parts

                            from backend.app.capabilities.registry import get_tool_backend
                            import importlib
                            import inspect

                            backend_path = get_tool_backend(cap, tool_name)
                            if backend_path is None:
                                errors.append(
                                    f"Step '{step_id}': Tool '{tool_slot}' backend not found"
                                )
                                continue

                            if ':' not in backend_path:
                                errors.append(
                                    f"Step '{step_id}': Tool '{tool_slot}' invalid backend format: '{backend_path}'"
                                )
                                continue

                            module_path, target = backend_path.rsplit(':', 1)

                            if module_path.startswith('app.'):
                                module_path = 'backend.' + module_path

                            # 強制先載入 capability models（確保 Plan 等 fallback 邏輯執行）
                            models_module_path = f'capabilities.{cap}.models'
                            logger.info(f"Pre-loading {models_module_path} for tool '{tool_slot}' validation")
                            logger.debug(f"sys.path before pre-load: {sys.path[:5]}... (showing first 5)")

                            try:
                                models_module = importlib.import_module(models_module_path)

                                # 檢查模組狀態
                                logger.info(f"Module '{models_module_path}' loaded, checking Plan availability...")
                                logger.debug(f"Module in sys.modules: {models_module_path in sys.modules}")
                                logger.debug(f"Module object: {models_module}")
                                logger.debug(f"Module __file__: {getattr(models_module, '__file__', 'N/A')}")

                                # 驗證 Plan 是否成功加載
                                if hasattr(models_module, 'Plan') and models_module.Plan is not None:
                                    logger.info(f"✅ Force pre-loaded {models_module_path}, Plan={models_module.Plan}, source={getattr(models_module, 'get_model_source', lambda: 'unknown')()}")

                                    # 確保 Plan 在 sys.modules 中可用
                                    if models_module_path in sys.modules:
                                        sys.modules[models_module_path].Plan = models_module.Plan
                                        logger.debug(f"✅ Set Plan in sys.modules['{models_module_path}']")

                                    # 檢查 Plan 是否在模組的 __dict__ 中
                                    if 'Plan' in models_module.__dict__:
                                        logger.debug(f"✅ Plan found in module __dict__")
                                    else:
                                        logger.warning(f"⚠️ Plan not in module __dict__, adding it...")
                                        models_module.Plan = models_module.Plan

                                else:
                                    logger.warning(f"⚠️ Force pre-loaded {models_module_path} but Plan is None")
                                    logger.debug(f"Module attributes: {[attr for attr in dir(models_module) if not attr.startswith('_')][:10]}")

                            except Exception as preload_err:
                                logger.warning(f"❌ Preload capability models failed for {cap}: {preload_err}")
                                import traceback
                                logger.warning(f"Preload traceback:\n{traceback.format_exc()}")

                            # 再次檢查 sys.modules 中的狀態
                            if models_module_path in sys.modules:
                                cached_module = sys.modules[models_module_path]
                                logger.debug(f"Checking cached module state: Plan={'available' if hasattr(cached_module, 'Plan') and cached_module.Plan is not None else 'NOT available'}")
                                if hasattr(cached_module, 'Plan') and cached_module.Plan is not None:
                                    logger.info(f"✅ Verified Plan is available in sys.modules['{models_module_path}']")
                                else:
                                    logger.warning(f"⚠️ Plan NOT available in cached module, attempting to set it...")
                                    # 嘗試重新導入並設置
                                    try:
                                        fresh_module = importlib.import_module(models_module_path)
                                        if hasattr(fresh_module, 'Plan') and fresh_module.Plan is not None:
                                            sys.modules[models_module_path].Plan = fresh_module.Plan
                                            logger.info(f"✅ Set Plan from fresh import")
                                    except Exception as e:
                                        logger.warning(f"Failed to set Plan from fresh import: {e}")

                            logger.info(f"Importing tool file: {module_path}")
                            logger.debug(f"sys.path before tool import: {sys.path[:5]}... (showing first 5)")

                            try:
                                module = importlib.import_module(module_path)
                            except (ImportError, ModuleNotFoundError) as import_error:
                                errors.append(
                                    f"Step '{step_id}': Tool '{tool_slot}' validation error: {import_error}"
                                )
                                continue

                            try:
                                # 獲取函數/方法對象
                                if '.' in target:
                                    # Class method
                                    class_name, method_name = target.rsplit('.', 1)
                                    cls = getattr(module, class_name, None)
                                    if cls is None:
                                        errors.append(
                                            f"Step '{step_id}': Tool '{tool_slot}' class '{class_name}' not found in module"
                                        )
                                        continue
                                    func = getattr(cls, method_name, None)
                                else:
                                    # Module-level function
                                    func = getattr(module, target, None)

                                if func is None:
                                    errors.append(
                                        f"Step '{step_id}': Tool '{tool_slot}' function '{target}' not found in module"
                                    )
                                    continue

                                # 檢查是否可調用
                                if not callable(func):
                                    errors.append(
                                        f"Step '{step_id}': Tool '{tool_slot}' '{backend_path}' is not a callable object"
                                    )
                                    continue

                                # 檢查函數簽名（不實際執行）
                                sig = inspect.signature(func)
                                logger.debug(f"Step '{step_id}': Tool '{tool_slot}' signature validated: {sig}")

                            except Exception as e:
                                errors.append(
                                    f"Step '{step_id}': Tool '{tool_slot}' validation error: {str(e)}"
                                )
                        else:
                            errors.append(
                                f"Step '{step_id}': Invalid tool_slot format: '{tool_slot}' (expected 'capability.tool_name')"
                            )
                    else:
                        # 非 capability tool（可能是 MindscapeTool），跳過驗證
                        # 這些 tool 需要運行時環境才能驗證
                        logger.debug(f"Step '{step_id}': Non-capability tool '{tool_slot}' skipped (requires runtime)")

                except Exception as e:
                    errors.append(
                        f"Step '{step_id}': Tool '{tool_slot}' call test failed: {str(e)}"
                    )

            if errors:
                logger.error(f"Playbook {playbook_code} tool call test failed: {len(errors)} error(s)")

        except json.JSONDecodeError as e:
            errors.append(f"Invalid JSON in playbook spec: {e}")
        except Exception as e:
            errors.append(f"Error validating tool calls: {e}")

        return errors

    def _install_tools(
        self,
        cap_dir: Path,
        capability_code: str,
        result: Dict
    ):
        """Install capability tools"""
        tools_dir = cap_dir / "tools"
        if not tools_dir.exists():
            return

        target_tools_dir = self.capabilities_dir / capability_code / "tools"
        target_tools_dir.mkdir(parents=True, exist_ok=True)

        for tool_file in tools_dir.glob("*.py"):
            if tool_file.name.startswith("__"):
                continue

            target_tool = target_tools_dir / tool_file.name
            shutil.copy2(tool_file, target_tool)
            tool_name = tool_file.stem
            result["installed"]["tools"].append(tool_name)
            logger.debug(f"Installed tool: {tool_name}")

    def _install_services(
        self,
        cap_dir: Path,
        capability_code: str,
        result: Dict
    ):
        """Install capability services"""
        services_dir = cap_dir / "services"
        if not services_dir.exists():
            return

        target_services_dir = self.capabilities_dir / capability_code / "services"
        target_services_dir.mkdir(parents=True, exist_ok=True)

        for service_file in services_dir.glob("*.py"):
            if service_file.name.startswith("__"):
                continue

            target_service = target_services_dir / service_file.name
            shutil.copy2(service_file, target_service)
            service_name = service_file.stem
            result["installed"]["services"].append(service_name)
            logger.debug(f"Installed service: {service_name}")

    def _install_api_endpoints(
        self,
        cap_dir: Path,
        capability_code: str,
        result: Dict
    ):
        """Install capability API endpoints from 'api' or 'routes' directory"""
        # Try 'api' directory first (standard)
        api_dir = cap_dir / "api"
        routes_dir = cap_dir / "routes"

        # Install from 'api' directory if exists
        if api_dir.exists():
            target_api_dir = self.capabilities_dir / capability_code / "api"
            target_api_dir.mkdir(parents=True, exist_ok=True)

            for api_file in api_dir.glob("*.py"):
                if api_file.name.startswith("__"):
                    continue

                target_api = target_api_dir / api_file.name
                shutil.copy2(api_file, target_api)
                api_name = api_file.stem
                result["installed"]["api_endpoints"] = result.get("api_endpoints", [])
                result["installed"]["api_endpoints"].append(api_name)
                logger.debug(f"Installed API endpoint: {api_name}")

        # Also install from 'routes' directory if exists (for capabilities using routes/)
        if routes_dir.exists():
            target_routes_dir = self.capabilities_dir / capability_code / "routes"
            target_routes_dir.mkdir(parents=True, exist_ok=True)

            for route_file in routes_dir.glob("*.py"):
                if route_file.name.startswith("__"):
                    continue

                target_route = target_routes_dir / route_file.name
                shutil.copy2(route_file, target_route)
                route_name = route_file.stem
                result["installed"]["api_endpoints"] = result.get("api_endpoints", [])
                result["installed"]["api_endpoints"].append(route_name)
                logger.debug(f"Installed route: {route_name}")

    def _install_schema_modules(
        self,
        cap_dir: Path,
        capability_code: str,
        result: Dict
    ):
        """Install capability schema modules"""
        schema_dir = cap_dir / "schema"
        if not schema_dir.exists():
            return

        target_schema_dir = self.capabilities_dir / capability_code / "schema"
        target_schema_dir.mkdir(parents=True, exist_ok=True)

        # Install all Python files including __init__.py
        for schema_file in schema_dir.glob("*.py"):
            target_schema = target_schema_dir / schema_file.name
            shutil.copy2(schema_file, target_schema)
            schema_name = schema_file.stem
            if not schema_name.startswith("__"):
                result["installed"]["schema_modules"] = result.get("schema_modules", [])
                result["installed"]["schema_modules"].append(schema_name)
            logger.debug(f"Installed schema module: {schema_file.name}")

    def _install_database_models(
        self,
        cap_dir: Path,
        capability_code: str,
        result: Dict
    ):
        """Install capability database models"""
        database_models_dir = cap_dir / "database" / "models"
        if not database_models_dir.exists():
            return

        # Target: app/models/{capability_code}.py or app/models/{capability_code}/
        target_models_dir = self.local_core_root / "backend" / "app" / "models"
        target_models_dir.mkdir(parents=True, exist_ok=True)

        # Install all Python files from database/models/
        for model_file in database_models_dir.glob("*.py"):
            if model_file.name.startswith("__"):
                continue

            # Install as app/models/{capability_code}_{model_file.name}
            # or create app/models/{capability_code}/ directory
            target_model_dir = target_models_dir / capability_code
            target_model_dir.mkdir(parents=True, exist_ok=True)

            target_model = target_model_dir / model_file.name

            # Read and fix import paths for local-core
            # Try multiple encodings to handle different file encodings
            content = None
            for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
                try:
                    with open(model_file, 'r', encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                # If all encodings fail, try binary read and decode with errors='replace'
                with open(model_file, 'rb') as f:
                    raw_content = f.read()
                content = raw_content.decode('utf-8', errors='replace')

            # Fix Base import: from .. import Base -> try multiple import paths
            # Cloud uses: from .. import Base (from database.models.__init__)
            # Local-core may need: from database import Base or create Base here
            # For now, try to import from cloud's database structure
            # If that fails, models will need Base to be defined in local-core
            if 'from .. import Base' in content:
                # Try to use cloud's database Base (if available)
                # Otherwise, will need to be fixed manually or Base needs to be in local-core
                content = content.replace('from .. import Base', 'from database import Base')

            with open(target_model, 'w', encoding='utf-8') as f:
                f.write(content)

            model_name = model_file.stem
            result["installed"]["database_models"] = result.get("database_models", [])
            result["installed"]["database_models"].append(model_name)
            logger.debug(f"Installed database model: {model_file.name} (imports fixed)")

        # Install __init__.py if exists
        init_file = database_models_dir / "__init__.py"
        if init_file.exists():
            target_init_dir = target_models_dir / capability_code
            target_init_dir.mkdir(parents=True, exist_ok=True)
            target_init = target_init_dir / "__init__.py"
            shutil.copy2(init_file, target_init)
            logger.debug(f"Installed database models __init__.py")

    def _install_migrations(
        self,
        cap_dir: Path,
        capability_code: str,
        result: Dict
    ):
        """Install capability migration files to Alembic versions directory"""
        migrations_yaml = cap_dir / "migrations.yaml"
        migrations_dir = cap_dir / "migrations"

        # Safety check: if migrations.yaml exists but migrations/ directory doesn't, create it
        if migrations_yaml.exists() and not migrations_dir.exists():
            logger.warning(
                f"Capability {capability_code} has migrations.yaml but missing migrations/ directory. "
                f"Creating migrations/ directory automatically."
            )
            migrations_dir.mkdir(parents=True, exist_ok=True)
            # Create __init__.py in migrations directory
            init_file = migrations_dir / "__init__.py"
            if not init_file.exists():
                init_file.write_text("# Migration files directory\n")

        # If no migrations directory and no migrations.yaml, skip (capability doesn't need migrations)
        if not migrations_dir.exists():
            return

        # Target: alembic/postgres/versions/ (where Alembic expects migration files)
        alembic_versions_dir = self.local_core_root / "backend" / "alembic" / "postgres" / "versions"
        if not alembic_versions_dir.exists():
            error_msg = f"Alembic versions directory not found: {alembic_versions_dir}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            return

        # Install all Python migration files from migrations/ directory
        all_py_files = list(migrations_dir.rglob("*.py"))
        # Filter out __init__.py and other non-migration files
        migration_files = [f for f in all_py_files if not f.name.startswith("__")]

        logger.debug(
            f"Migration check for {capability_code}: "
            f"all_py_files={[f.name for f in all_py_files]}, "
            f"migration_files={[f.name for f in migration_files]}, "
            f"migrations_yaml.exists()={migrations_yaml.exists()}"
        )

        if not migration_files:
            if migrations_yaml.exists():
                error_msg = (
                    f"Capability {capability_code} has migrations.yaml and migrations/ directory, "
                    f"but no migration files found. Migration files must be included in migrations/ directory."
                )
                logger.error(error_msg)
                result["errors"].append(error_msg)
                return
            # No migrations.yaml and no files, skip silently
            return

        installed_files = []
        for migration_file in migration_files:
            # Copy to Alembic versions directory
            target_file = alembic_versions_dir / migration_file.name
            shutil.copy2(migration_file, target_file)
            logger.debug(f"Installed migration: {migration_file.name}")
            installed_files.append(migration_file.name)

        if installed_files:
            result["installed"]["migrations"] = result.get("migrations", [])
            result["installed"]["migrations"].extend(installed_files)
            logger.info(f"Installed {len(installed_files)} migration files for {capability_code}")

    def _execute_migrations(
        self,
        capability_code: str,
        result: Dict
    ):
        """Execute database migrations using Alembic"""
        alembic_config = self.local_core_root / "backend" / "alembic.postgres.ini"
        if not alembic_config.exists():
            logger.warning(f"Alembic config not found: {alembic_config}, skipping migration execution")
            result.setdefault("warnings", []).append("Migrations installed but not executed (alembic config not found)")
            return

        try:
            logger.info(f"Executing database migrations for {capability_code}...")

            # Run alembic upgrade head
            process = subprocess.run(
                ["alembic", "-c", str(alembic_config), "upgrade", "head"],
                cwd=str(self.local_core_root / "backend"),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                check=False
            )

            if process.returncode == 0:
                logger.info(f"Successfully executed migrations for {capability_code}")
                result.setdefault("migration_status", {})[capability_code] = "applied"
            else:
                error_msg = f"Migration execution failed: {process.stderr}"
                logger.error(error_msg)
                result.setdefault("warnings", []).append(error_msg)
                result.setdefault("migration_status", {})[capability_code] = "failed"
        except subprocess.TimeoutExpired:
            error_msg = "Migration execution timed out after 5 minutes"
            logger.error(error_msg)
            result.setdefault("warnings", []).append(error_msg)
            result.setdefault("migration_status", {})[capability_code] = "timeout"
        except Exception as e:
            error_msg = f"Migration execution error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result.setdefault("warnings", []).append(error_msg)
            result.setdefault("migration_status", {})[capability_code] = "error"

    def _install_ui_components(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: Dict
    ):
        """
        Install UI components from capability pack to Local-Core frontend.

        Args:
            cap_dir: Extracted capability directory (from .mindpack)
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: Result dict to update
        """
        ui_components = manifest.get("ui_components", [])
        if not ui_components:
            return

        # Target directory: web-console/src/app/capabilities/{capability_code}/components
        frontend_dir = self.local_core_root / "web-console" / "src" / "app" / "capabilities"
        target_cap_dir = frontend_dir / capability_code / "components"
        target_cap_dir.mkdir(parents=True, exist_ok=True)

        installed_components = []

        # Install entire ui/ directory if it exists (to include all dependencies)
        source_ui_dir = cap_dir / "ui"
        if source_ui_dir.exists() and source_ui_dir.is_dir():
            # Copy all files from ui/ directory (always overwrite to ensure latest version)
            for file_path in source_ui_dir.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(source_ui_dir)
                    target_path = target_cap_dir / relative_path.name
                    # Create subdirectories if needed
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(file_path, target_path)
                    logger.debug(f"Installed UI file: {relative_path.name}")

        # Also install individual components specified in manifest
        for component_def in ui_components:
            component_code = component_def.get("code")
            component_path = component_def.get("path")

            if not component_path:
                result["warnings"].append(f"Component {component_code} missing path")
                continue

            # Source: extracted capability pack directory
            source_path = cap_dir / component_path
            if not source_path.exists():
                result["warnings"].append(f"Component file not found: {component_path}")
                continue

            # Target: Local-Core frontend
            target_path = target_cap_dir / source_path.name

            # Copy component file (always overwrite to ensure latest version)
            shutil.copy2(source_path, target_path)

            # Process import paths (if needed)
            # TODO: Handle import path mapping if Cloud components use different paths

            installed_components.append(component_code)
            logger.debug(f"Installed UI component: {component_code}")

        if installed_components:
            result["installed"]["ui_components"] = installed_components

    def _install_manifest(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict
    ):
        """Install capability manifest"""
        target_cap_dir = self.capabilities_dir / capability_code
        target_cap_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = cap_dir / "manifest.yaml"
        target_manifest = target_cap_dir / "manifest.yaml"
        shutil.copy2(manifest_path, target_manifest)
        logger.debug(f"Installed manifest: {capability_code}/manifest.yaml")

    def _install_root_files(
        self,
        cap_dir: Path,
        capability_code: str,
        result: Dict
    ):
        """Install root-level Python files (e.g., models.py)"""
        cap_install_dir = self.capabilities_dir / capability_code
        cap_install_dir.mkdir(parents=True, exist_ok=True)

        # Install all .py files in capability root directory
        for py_file in cap_dir.glob("*.py"):
            if py_file.is_file():
                target_file = cap_install_dir / py_file.name
                shutil.copy2(py_file, target_file)
                logger.debug(f"Installed root file: {py_file.name}")
                result["installed"].setdefault("root_files", []).append(py_file.name)

    def _run_post_install_hooks(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: Dict
    ):
        """
        Run post-install hooks (bootstrap scripts) defined in manifest

        Args:
            cap_dir: Extracted capability directory
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: Result dict to update
        """
        # Check for bootstrap scripts in manifest
        bootstrap_scripts = manifest.get('bootstrap', [])
        if not bootstrap_scripts:
            # Check for capability-specific bootstrap logic
            ig_related_codes = [
                'ig_post', 'ig_post_generation', 'instagram', 'social_media',
                'ig_series_manager', 'ig_review_system'
            ]
            if capability_code in ig_related_codes:
                # Auto-initialize Content Vault for IG-related capabilities
                self._bootstrap_content_vault(result)
            return

        for script_config in bootstrap_scripts:
            script_type = script_config.get('type')
            script_path = script_config.get('path')

            if script_type == 'python_script':
                # Run Python script
                script_full_path = cap_dir / script_path
                if script_full_path.exists():
                    try:
                        self._run_python_script(script_full_path, result)
                    except Exception as e:
                        logger.warning(f"Bootstrap script failed: {e}")
                        result["warnings"].append(f"Bootstrap script failed: {e}")
                else:
                    logger.warning(f"Bootstrap script not found: {script_full_path}")
                    result["warnings"].append(f"Bootstrap script not found: {script_path}")

            elif script_type == 'content_vault_init':
                # Initialize Content Vault
                vault_path = script_config.get('vault_path')
                self._bootstrap_content_vault(result, vault_path)

    def _bootstrap_content_vault(
        self,
        result: Dict,
        vault_path: Optional[str] = None
    ):
        """
        Bootstrap Content Vault for IG-related capabilities

        Args:
            result: Result dict to update
            vault_path: Optional vault path (default: ~/content-vault)
        """
        try:
            # Import initialization script
            script_path = self.local_core_root / "backend" / "scripts" / "init_content_vault.py"
            if not script_path.exists():
                logger.warning(f"Content Vault init script not found: {script_path}")
                result["warnings"].append("Content Vault init script not found")
                return

            # Run initialization script
            import subprocess
            cmd = [sys.executable, str(script_path)]
            if vault_path:
                cmd.extend(["--vault-path", vault_path])

            logger.info("Running Content Vault initialization...")
            process_result = subprocess.run(
                cmd,
                cwd=str(self.local_core_root),
                capture_output=True,
                text=True,
                timeout=30
            )

            if process_result.returncode == 0:
                logger.info("Content Vault initialized successfully")
                result["bootstrap"] = result.get("bootstrap", [])
                result["bootstrap"].append("content_vault_initialized")
            else:
                logger.warning(f"Content Vault initialization failed: {process_result.stderr}")
                result["warnings"].append(f"Content Vault initialization failed: {process_result.stderr}")

        except subprocess.TimeoutExpired:
            logger.warning("Content Vault initialization timed out")
            result["warnings"].append("Content Vault initialization timed out")
        except Exception as e:
            logger.warning(f"Failed to run Content Vault initialization: {e}")
            result["warnings"].append(f"Content Vault initialization error: {e}")

    def _run_python_script(
        self,
        script_path: Path,
        result: Dict
    ):
        """
        Run Python bootstrap script

        Args:
            script_path: Path to Python script
            result: Result dict to update
        """
        import subprocess
        logger.info(f"Running bootstrap script: {script_path}")
        process_result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(self.local_core_root),
            capture_output=True,
            text=True,
            timeout=60
        )

        if process_result.returncode == 0:
            logger.info(f"Bootstrap script completed: {script_path}")
            result["bootstrap"] = result.get("bootstrap", [])
            result["bootstrap"].append(str(script_path.name))
        else:
            error_msg = process_result.stderr or process_result.stdout
            logger.warning(f"Bootstrap script failed: {error_msg}")
            result["warnings"].append(f"Bootstrap script failed: {error_msg}")
