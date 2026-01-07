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
from .bootstrap.bootstrap_registry import BootstrapRegistry
from .post_install_modules.dependency_installer import DependencyInstaller
from .post_install_modules.dependency_checker import DependencyChecker
from .post_install_modules.degradation_registrar import DegradationRegistrar
from .post_install_modules.playbook_validator import PlaybookValidator

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

        # Initialize modular components
        self.dependency_installer = DependencyInstaller(local_core_root)
        self.dependency_checker = DependencyChecker()
        self.degradation_registrar = DegradationRegistrar()
        self.playbook_validator = PlaybookValidator(
            local_core_root,
            capabilities_dir,
            validate_tools_direct_call_func
        )

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
        self.dependency_installer.install_python_dependencies(cap_dir, capability_code, result)

        logger.info(f"[{capability_code}] Starting UI dependencies installation...")
        self.dependency_installer.install_ui_dependencies(capability_code, manifest, result)
        logger.info(f"[{capability_code}] Completed UI dependencies installation")

        missing_required, missing_optional, missing_external, missing_system_tools, degraded_features_map = \
            self.dependency_checker.check_dependencies(manifest, result)

        if missing_required or missing_optional or missing_external or missing_system_tools:
            capability_code = result.capability_code
            if capability_code:
                self.degradation_registrar.register_degradation_status(
                    capability_code,
                    manifest,
                    missing_required,
                    missing_optional + missing_external + missing_system_tools,
                    degraded_features_map,
                    result
                )

        self.run_post_install_hooks(cap_dir, capability_code, manifest, result)
        self.playbook_validator.validate_installed_playbooks(capability_code, manifest, result)

    def run_post_install_hooks(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult
    ):
        """
        Run post-install hooks (bootstrap scripts) defined in manifest

        Uses strategy pattern to handle bootstrap operations. All configurations
        are declared through manifest, avoiding hardcoded capability code lists.

        Args:
            cap_dir: Extracted capability directory
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: InstallResult to update
        """
        bootstrap_scripts = manifest.get('bootstrap', [])
        if not bootstrap_scripts:
            logger.debug(f"No bootstrap scripts defined for {capability_code}")
            return

        registry = BootstrapRegistry()

        for script_config in bootstrap_scripts:
            script_type = script_config.get('type')
            if not script_type:
                logger.warning("Bootstrap config missing 'type' field")
                result.add_warning("Bootstrap config missing 'type' field")
                continue

            strategy = registry.get_strategy(script_type)
            if not strategy:
                logger.warning(f"Unknown bootstrap strategy type: {script_type}")
                result.add_warning(f"Unknown bootstrap strategy type: {script_type}")
                continue

            try:
                strategy.execute(
                    self.local_core_root,
                    cap_dir,
                    capability_code,
                    script_config,
                    result
                )
            except Exception as e:
                logger.warning(f"Bootstrap strategy '{script_type}' failed: {e}")
                result.add_warning(f"Bootstrap strategy '{script_type}' failed: {str(e)[:200]}")

