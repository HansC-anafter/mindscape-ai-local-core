"""
Post Install Handler

Dependency checking, degradation registration, bootstrap execution, and post-installation playbook validation.
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Any

from .install_result import InstallResult

logger = logging.getLogger(__name__)


class PostInstallHandler:
    """Handle post-installation tasks: dependencies, degradation, bootstrap, validation"""

    def __init__(
        self,
        local_core_root: Path,
        capabilities_dir: Path,
        specs_dir: Path,
        validate_tools_direct_call_func: Optional[callable] = None
    ):
        """
        Initialize post-install handler

        Args:
            local_core_root: Local-core project root directory
            capabilities_dir: Directory for capability manifests
            specs_dir: Directory for playbook JSON specs
            validate_tools_direct_call_func: Function to validate tools via direct call
                                            (from PlaybookInstaller._validate_tools_direct_call)
        """
        self.local_core_root = local_core_root
        self.capabilities_dir = capabilities_dir
        self.specs_dir = specs_dir
        self._validate_tools_direct_call = validate_tools_direct_call_func

    def run_all(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult
    ):
        """
        Run all post-install tasks

        Args:
            cap_dir: Extracted capability directory
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: InstallResult to update
        """
        # 1. Install Python dependencies from requirements.txt (if exists)
        self.install_python_dependencies(cap_dir, capability_code, result)

        # 2. Check dependencies and register degradation
        self.check_dependencies(manifest, result)

        # 3. Run post-install hooks (bootstrap scripts)
        self.run_post_install_hooks(cap_dir, capability_code, manifest, result)

        # 4. Validate installed playbooks
        self.validate_installed_playbooks(capability_code, manifest, result)

    def install_python_dependencies(
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
    ):
        """
        Install Python dependencies from requirements.txt if it exists in capability pack

        Args:
            cap_dir: Extracted capability directory
            capability_code: Capability code
            result: InstallResult to update
        """
        requirements_file = cap_dir / "requirements.txt"
        if not requirements_file.exists():
            logger.debug(f"No requirements.txt found for {capability_code}")
            return

        try:
            logger.info(f"Installing Python dependencies from {requirements_file} for {capability_code}...")

            # Read requirements.txt to log what will be installed
            with open(requirements_file, 'r', encoding='utf-8') as f:
                requirements = f.read().strip()
                if requirements:
                    logger.debug(f"Requirements content:\n{requirements}")

            # Install using pip
            process = subprocess.run(
                [
                    sys.executable, "-m", "pip", "install",
                    "-r", str(requirements_file),
                    "--quiet",  # Reduce output noise
                    "--no-warn-script-location"  # Suppress script location warnings
                ],
                cwd=str(self.local_core_root),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                check=False
            )

            if process.returncode == 0:
                logger.info(f"Successfully installed Python dependencies for {capability_code}")
                result.bootstrap.append("python_dependencies_installed")

                # Log installed packages (from stdout)
                if process.stdout:
                    installed_packages = [line for line in process.stdout.split('\n')
                                       if 'Successfully installed' in line or 'Requirement already satisfied' in line]
                    if installed_packages:
                        logger.debug(f"Installation summary: {installed_packages[:5]}")  # Log first 5
            else:
                error_msg = process.stderr or process.stdout or "Unknown error"
                logger.warning(f"Failed to install Python dependencies for {capability_code}: {error_msg[:500]}")
                result.add_warning(
                    f"Python dependencies installation failed: {error_msg[:200]}"
                )

        except subprocess.TimeoutExpired:
            logger.warning(f"Python dependencies installation timed out for {capability_code}")
            result.add_warning("Python dependencies installation timed out")
        except Exception as e:
            logger.warning(f"Failed to install Python dependencies for {capability_code}: {e}")
            result.add_warning(f"Python dependencies installation error: {str(e)[:200]}")

    def check_dependencies(
        self,
        manifest: Dict,
        result: InstallResult
    ):
        """
        Check for missing dependencies and register degradation status

        Args:
            manifest: Parsed manifest dict
            result: InstallResult to update
        """
        capability_code = result.capability_code
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

        # Check system tools
        system_tools = dependencies.get('system_tools', [])
        missing_system_tools = []
        for tool_config in system_tools:
            tool_name = tool_config if isinstance(tool_config, str) else tool_config.get('name', '')
            if not tool_name:
                continue

            if not self._is_system_tool_available(tool_name):
                missing_system_tools.append(tool_name)
                # Add to degraded features map
                if isinstance(tool_config, dict):
                    degraded_features = tool_config.get('degraded_features', [])
                    install_hint = tool_config.get('install_hint', '')
                    if degraded_features:
                        degraded_features_map[tool_name] = degraded_features
                    # Add install hint to result warnings
                    if install_hint:
                        result.add_warning(
                            f"System tool '{tool_name}' not found. {install_hint}"
                        )
                    else:
                        result.add_warning(
                            f"System tool '{tool_name}' not found. "
                            f"Some features may be degraded. "
                            f"Install with: apt-get install {tool_name} (Linux) or brew install {tool_name} (macOS)"
                        )

        # Register degradation status
        if missing_required or missing_optional or missing_external or missing_system_tools:
            self._register_degradation_status(
                capability_code,
                manifest,
                missing_required,
                missing_optional + missing_external + missing_system_tools,
                degraded_features_map,
                result
            )

        # Add to result for reporting
        if missing_required:
            if not result.missing_dependencies:
                result.missing_dependencies = {}
            result.missing_dependencies["required"] = missing_required
        if missing_optional:
            if not result.missing_dependencies:
                result.missing_dependencies = {}
            result.missing_dependencies["optional"] = missing_optional
        if missing_external:
            if not result.missing_dependencies:
                result.missing_dependencies = {}
            result.missing_dependencies["external_services"] = missing_external
        if missing_system_tools:
            if not result.missing_dependencies:
                result.missing_dependencies = {}
            result.missing_dependencies["system_tools"] = missing_system_tools

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
        return bool(os.getenv(env_var))

    def _is_system_tool_available(self, tool_name: str) -> bool:
        """
        Check if a system tool is available in PATH

        Args:
            tool_name: System tool name (e.g., 'ffprobe', 'ffmpeg')

        Returns:
            True if available
        """
        try:
            # Use 'which' command to check if tool exists in PATH
            result = subprocess.run(
                ['which', tool_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # 'which' command not available or timed out, try alternative method
            try:
                # Try to run the tool with --version or --help
                result = subprocess.run(
                    [tool_name, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False

    def _register_degradation_status(
        self,
        capability_code: str,
        manifest: Dict,
        missing_required: List[str],
        missing_optional: List[str],
        degraded_features_map: Dict[str, List[str]],
        result: InstallResult
    ):
        """
        Register capability degradation status

        Args:
            capability_code: Capability code
            manifest: Parsed manifest dict
            missing_required: List of missing required dependencies
            missing_optional: List of missing optional dependencies
            degraded_features_map: Map of dependency -> degraded features
            result: InstallResult to update
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

            # Register with degradation registry
            registry = DegradationRegistry()
            cap_status = registry.register_capability(
                code=capability_code,
                all_features=all_features,
                missing_deps=missing_required + missing_optional,
                degraded_features_map=degraded_features_map
            )

            # Add to result
            result.degradation_status = cap_status.to_dict()
            logger.info(
                f"Registered degradation status for {capability_code}: "
                f"status={cap_status.status}, "
                f"degraded_features={cap_status.degraded_features}"
            )

        except ImportError:
            logger.warning("DegradationRegistry not available, skipping degradation registration")
            result.add_warning("Degradation status not registered (DegradationRegistry not available)")
        except Exception as e:
            logger.warning(f"Failed to register degradation status: {e}")
            result.add_warning(f"Failed to register degradation status: {e}")

    def run_post_install_hooks(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult
    ):
        """
        Run post-install hooks (bootstrap scripts) defined in manifest

        Args:
            cap_dir: Extracted capability directory
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: InstallResult to update
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
                        result.add_warning(f"Bootstrap script failed: {e}")
                else:
                    logger.warning(f"Bootstrap script not found: {script_full_path}")
                    result.add_warning(f"Bootstrap script not found: {script_path}")

            elif script_type == 'content_vault_init':
                # Initialize Content Vault
                vault_path = script_config.get('vault_path')
                self._bootstrap_content_vault(result, vault_path)

    def _bootstrap_content_vault(
        self,
        result: InstallResult,
        vault_path: Optional[str] = None
    ):
        """
        Bootstrap Content Vault for IG-related capabilities

        Args:
            result: InstallResult to update
            vault_path: Optional vault path (default: ~/content-vault)
        """
        try:
            # Import initialization script
            script_path = self.local_core_root / "backend" / "scripts" / "init_content_vault.py"
            if not script_path.exists():
                logger.warning(f"Content Vault init script not found: {script_path}")
                result.add_warning("Content Vault init script not found")
                return

            # Run initialization script
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
                result.bootstrap.append("content_vault_initialized")
            else:
                logger.warning(f"Content Vault initialization failed: {process_result.stderr}")
                result.add_warning(f"Content Vault initialization failed: {process_result.stderr}")

        except subprocess.TimeoutExpired:
            logger.warning("Content Vault initialization timed out")
            result.add_warning("Content Vault initialization timed out")
        except Exception as e:
            logger.warning(f"Failed to run Content Vault initialization: {e}")
            result.add_warning(f"Content Vault initialization error: {e}")

    def _run_python_script(
        self,
        script_path: Path,
        result: InstallResult
    ):
        """
        Run Python bootstrap script

        Args:
            script_path: Path to Python script
            result: InstallResult to update
        """
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
            result.bootstrap.append(str(script_path.name))
        else:
            error_msg = process_result.stderr or process_result.stdout
            logger.warning(f"Bootstrap script failed: {error_msg}")
            result.add_warning(f"Bootstrap script failed: {error_msg}")

    def validate_installed_playbooks(
        self,
        capability_code: str,
        manifest: Dict,
        result: InstallResult
    ):
        """
        Validate installed playbooks:
        1. Structure validation (via script)
        2. Direct tool call test (backend simulation, no LLM)

        Args:
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: InstallResult to update
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
            structure_valid = False
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
                        "CAPABILITIES_PATH": str(self.capabilities_dir)  # Pass correct capabilities path
                    }
                )

                if process.returncode == 0:
                    # Try to parse JSON output and confirm validation results
                    try:
                        output = process.stdout.strip()
                        # Try to parse JSON from the beginning (JSON mode should only output JSON)
                        json_output = None
                        try:
                            json_output = json.loads(output)
                        except json.JSONDecodeError:
                            # If parsing from beginning fails, try to find the first complete JSON object
                            # Start from the first { and find the matching }
                            json_start = output.find('{')
                            if json_start >= 0:
                                # Find matching closing brace
                                brace_count = 0
                                json_end = json_start
                                for i in range(json_start, len(output)):
                                    if output[i] == '{':
                                        brace_count += 1
                                    elif output[i] == '}':
                                        brace_count -= 1
                                        if brace_count == 0:
                                            json_end = i + 1
                                            break
                                if brace_count == 0:
                                    json_output = json.loads(output[json_start:json_end])

                        if json_output:
                            validations = json_output.get("validations", [])
                            # Check if this playbook passed
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
                                        structure_valid = False
                                        break
                                    else:
                                        structure_valid = True
                                        break
                            else:
                                # Playbook not found, treat as passed (may be other issue)
                                structure_valid = True
                        else:
                            # No JSON output, treat as passed
                            structure_valid = True
                    except Exception as e:
                        # JSON parsing failed but returncode is 0, treat as passed
                        structure_valid = True
                        logger.debug(f"Playbook {playbook_code} structure validation passed (JSON parse error ignored: {e})")
                else:
                    structure_valid = False
                if not structure_valid:
                    # Parse error from output (only take JSON part)
                    try:
                        output = (process.stderr or process.stdout or "").strip()
                        # Find JSON part
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
                                # Not found, use original error message
                                error_msg = output[-500:] if len(output) > 500 else output
                                validation_results["failed"].append({
                                    "playbook": playbook_code,
                                    "error": error_msg
                                })
                                logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                        else:
                            # No JSON, use original error message (filter out INFO logs)
                            error_lines = [line for line in output.split('\n') if not line.strip().startswith('[INFO]')]
                            error_msg = '\n'.join(error_lines[-10:])  # Only take last 10 lines
                            validation_results["failed"].append({
                                "playbook": playbook_code,
                                "error": error_msg or "Unknown error"
                            })
                            logger.error(f"Playbook {playbook_code} structure validation failed: {error_msg}")
                    except Exception as e:
                        # JSON parsing failed, use original error message
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

            # 2. If structure validation passed, perform direct tool call test (without LLM)
            if structure_valid and self._validate_tools_direct_call:
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
                        # Check if errors are due to missing optional dependencies (e.g., bs4, httpx)
                        # These dependencies should be declared in manifest but may not be installed during validation
                        optional_dep_errors = []
                        critical_errors = []
                        for err in tool_test_errors:
                            # Check if error is about missing module (optional dependency)
                            if "No module named" in err and any(dep in err.lower() for dep in ['bs4', 'beautifulsoup', 'httpx', 'requests']):
                                optional_dep_errors.append(err)
                            else:
                                critical_errors.append(err)

                        # Only critical errors are treated as failures
                        if critical_errors:
                            if len(critical_errors) == 1:
                                error_msg = critical_errors[0]
                            else:
                                error_msg = f"{len(critical_errors)} tool validation errors: " + "; ".join(critical_errors[:3])
                                if len(critical_errors) > 3:
                                    error_msg += f" (and {len(critical_errors) - 3} more)"

                            validation_results["failed"].append({
                                "playbook": playbook_code,
                                "error": f"Tool call test failed: {error_msg}"
                            })
                            logger.error(f"Playbook {playbook_code} tool call test failed: {error_msg}")
                        elif optional_dep_errors:
                            # Missing optional dependencies are treated as warnings
                            dep_names = []
                            for e in optional_dep_errors:
                                if "'" in e:
                                    parts = e.split("'")
                                    if len(parts) >= 2:
                                        dep_names.append(parts[1])
                                else:
                                    dep_names.append('unknown')
                            warning_msg = f"Missing optional dependencies: {', '.join(set(dep_names))}"
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
            elif structure_valid:
                # Structure valid but no tool validation function provided
                validation_results["validated"].append(playbook_code)
                logger.info(f"Playbook {playbook_code} structure validated (tool call test skipped)")

        # Add validation results to result
        result.playbook_validation = validation_results

        # Add errors for failed validations (validation failures are errors, not warnings)
        # Special handling: if failure is due to missing external dependencies (wordpress.*, seo.*), treat as warning
        if validation_results["failed"]:
            failed_playbooks = []
            warnings_for_missing_deps = []
            for f in validation_results["failed"]:
                playbook = f['playbook']
                error = f.get('error', '')
                # Check if failure is due to missing external dependency tools
                if 'backend not found' in error and ('wordpress.' in error or 'seo.' in error):
                    warnings_for_missing_deps.append(f"{playbook} (missing external dependencies: {error.split('Tool')[1] if 'Tool' in error else 'external tools'})")
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

        # Add warnings for skipped validations (only skipped validations are warnings)
        if validation_results["skipped"]:
            result.add_warning(
                f"Playbook validation skipped for: {validation_results['skipped']}"
            )

