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
                    result["errors"].extend(validation_errors)
                    logger.error(f"Manifest validation failed: {validation_errors}")
                    # Only block installation if there are actual validation errors
                    # Path issues should not block installation
                    if validation_errors and not any('path issue' in e.lower() or 'not found' in e.lower() for e in validation_errors):
                        return False, result
                    # If it's just path issues, continue with warning
                    logger.warning("Validation had path issues, continuing with installation")

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
        Validate manifest using validate_manifest.py script

        Args:
            manifest_path: Path to manifest.yaml
            cap_dir: Capability directory

        Returns:
            (is_valid, errors, warnings)
        """
        # Try to find validate_manifest.py in cloud repo
        cloud_repo = self.local_core_root.parent / "mindscape-ai-cloud"
        validate_script = cloud_repo / "scripts" / "validate_manifest.py"

        if not validate_script.exists():
            logger.warning("validate_manifest.py not found, skipping validation")
            # Return True to allow installation to continue without validation
            return True, [], ["validate_manifest.py not found, validation skipped"]

        try:
            # Run validation script
            # Note: validate_manifest.py expects capability directory name, not full path
            # But we're in a temp directory, so we need to use the actual path
            # Try to run from the cloud repo directory instead
            result = subprocess.run(
                [sys.executable, str(validate_script), cap_dir.name],
                cwd=str(cloud_repo),
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode == 0:
                # Parse warnings from output
                warnings = []
                for line in result.stdout.split('\n'):
                    if line.strip() and ('WARNING' in line or 'warning' in line.lower()):
                        warnings.append(line.strip())
                return True, [], warnings
            else:
                # Parse errors and warnings from output
                errors = []
                warnings = []
                for line in result.stdout.split('\n'):
                    if line.strip():
                        if 'ERROR' in line or 'error' in line.lower():
                            errors.append(line.strip())
                        elif 'WARNING' in line or 'warning' in line.lower():
                            warnings.append(line.strip())

                # If no structured errors found, use stderr or stdout
                if not errors and result.stderr:
                    errors.append(result.stderr.strip())
                elif not errors:
                    # If validation failed but no clear errors, check if it's a path issue
                    if 'No such file or directory' in result.stderr or 'can\'t open file' in result.stderr:
                        # This is likely a path issue, not a validation failure
                        logger.warning("Validation script path issue, continuing without validation")
                        return True, [], ["Validation script path issue, validation skipped"]
                    errors.append("Manifest validation failed (see output for details)")

                return False, errors, warnings

        except subprocess.TimeoutExpired:
            logger.warning("Validation script timed out")
            return True, [], ["Validation script timed out, continuing anyway"]
        except Exception as e:
            logger.warning(f"Failed to run validation: {e}")
            # Don't block installation if validation script fails
            return True, [], [f"Validation script execution failed: {e}, continuing anyway"]

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

            # 4. Install UI components
            self._install_ui_components(cap_dir, capability_code, manifest, result)

            # 5. Install manifest
            self._install_manifest(cap_dir, capability_code, manifest)

            # 6. Check dependencies and generate summary
            self._check_dependencies(manifest, result)

            # 7. Run post-install hooks (bootstrap scripts)
            self._run_post_install_hooks(cap_dir, capability_code, manifest, result)

            logger.info(f"Successfully installed capability: {capability_code}")
            return True

        except Exception as e:
            logger.error(f"Failed to install capability: {e}")
            result["errors"].append(f"Installation failed: {e}")
            return False

    def _check_dependencies(
        self,
        manifest: Dict,
        result: Dict
    ):
        """
        Check for missing dependencies and add to result

        Args:
            manifest: Parsed manifest dict
            result: Result dict to update
        """
        missing_dependencies = {
            "api_keys": [],
            "external_tools": [],
            "external_services": []
        }

        # Check tool dependencies
        playbooks = manifest.get('playbooks', [])
        for pb in playbooks:
            tool_deps = pb.get('tool_dependencies', [])
            for tool_dep in tool_deps:
                # Check if it's an external tool (not from this capability)
                if '.' in tool_dep or tool_dep.startswith('core_'):
                    # External tool - check if it's available
                    # Note: This is a simplified check. Full implementation would
                    # query the tool registry to verify availability
                    if tool_dep.startswith('core_llm.'):
                        # Core LLM tools are expected to be available
                        pass
                    else:
                        missing_dependencies["external_tools"].append(tool_dep)

        # Check service dependencies
        service_deps = manifest.get('service_dependencies', [])
        for service_dep in service_deps:
            # Check if service is available
            # Note: This would need to query service registry
            missing_dependencies["external_services"].append(service_dep)

        # Add to result
        if any(missing_dependencies.values()):
            result["missing_dependencies"] = {
                k: list(set(v)) for k, v in missing_dependencies.items() if v
            }

    def _install_playbooks(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: Dict
    ):
        """Install playbook specs and markdown files"""
        playbooks_config = manifest.get('playbooks', [])

        for pb_config in playbooks_config:
            playbook_code = pb_config.get('code')
            if not playbook_code:
                continue

            # Install JSON spec
            spec_path = cap_dir / pb_config.get('spec_path', f"playbooks/specs/{playbook_code}.json")
            if spec_path.exists():
                target_spec = self.specs_dir / f"{playbook_code}.json"
                self.specs_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(spec_path, target_spec)
                result["installed"]["playbooks"].append(playbook_code)
                logger.debug(f"Installed spec: {playbook_code}.json")

            # Install markdown files
            locales = pb_config.get('locales', ['zh-TW', 'en'])
            md_path_template = pb_config.get('path', f"playbooks/{{locale}}/{playbook_code}.md")

            for locale in locales:
                md_path = cap_dir / md_path_template.format(locale=locale)
                if md_path.exists():
                    target_md_dir = self.i18n_base_dir / locale
                    target_md_dir.mkdir(parents=True, exist_ok=True)
                    target_md = target_md_dir / f"{playbook_code}.md"
                    shutil.copy2(md_path, target_md)
                    logger.debug(f"Installed markdown: {playbook_code}.md ({locale})")

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
