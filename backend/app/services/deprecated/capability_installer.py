"""
DEPRECATED: Capability Installer Service

This module is kept only as a legacy facade for older capability-pack flows.
New code should use the modular installers directly.
"""

import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union

import yaml

from ..bootstrap.bootstrap_strategies import ContentVaultInitStrategy
from ..install_result import InstallResult
from ..manifest_validator import ManifestValidator
from ..mindpack_extractor import MindpackExtractor
from ..post_install import PostInstallHandler
from ..post_install_modules.dependency_checker import DependencyChecker
from ..post_install_modules.degradation_registrar import DegradationRegistrar
from ..post_install_modules.playbook_validator import PlaybookValidator
from ..runtime_assets_installer import RuntimeAssetsInstaller
from .capability_installer_core import LegacyPlaybookInstallerAdapter

logger = logging.getLogger(__name__)

LegacyResult = Union[Dict, InstallResult]
_LEGACY_CONTENT_VAULT_CAPABILITIES = {
    "ig_post",
    "ig_post_generation",
    "instagram",
    "social_media",
    "ig_series_manager",
    "ig_review_system",
}


class CapabilityInstaller:
    """Legacy capability installer facade."""

    def __init__(
        self,
        local_core_root: Path,
        capabilities_dir: Optional[Path] = None,
        specs_dir: Optional[Path] = None,
        i18n_dir: Optional[Path] = None,
        tools_dir: Optional[Path] = None,
        services_dir: Optional[Path] = None,
    ):
        """
        Initialize the legacy installer facade.

        Args:
            local_core_root: Local-core project root directory.
            capabilities_dir: Directory for capability manifests.
            specs_dir: Directory for playbook JSON specs.
            i18n_dir: Base directory for localized playbook markdown.
            tools_dir: Reserved legacy option for capability tools.
            services_dir: Reserved legacy option for capability services.
        """
        self.local_core_root = local_core_root

        backend_dir = local_core_root / "backend"
        self.capabilities_dir = capabilities_dir or (backend_dir / "app" / "capabilities")
        self.specs_dir = specs_dir or (backend_dir / "playbooks" / "specs")
        self.i18n_base_dir = i18n_dir or (backend_dir / "i18n" / "playbooks")
        self.tools_base_dir = tools_dir
        self.services_base_dir = services_dir

        self._extractor = MindpackExtractor(local_core_root)
        self._manifest_validator = ManifestValidator(local_core_root)
        self._playbook_installer = LegacyPlaybookInstallerAdapter(
            local_core_root=local_core_root,
            capabilities_dir=self.capabilities_dir,
            specs_dir=self.specs_dir,
            i18n_base_dir=self.i18n_base_dir,
        )
        self._runtime_assets_installer = RuntimeAssetsInstaller(
            local_core_root=local_core_root,
            capabilities_dir=self.capabilities_dir,
        )
        self._dependency_checker = DependencyChecker()
        self._degradation_registrar = DegradationRegistrar()
        self._playbook_validator = PlaybookValidator(
            local_core_root=local_core_root,
            capabilities_dir=self.capabilities_dir,
            validate_tools_direct_call_func=self._playbook_installer.validate_tools_direct_call,
        )
        self._post_install_handler = PostInstallHandler(
            local_core_root=local_core_root,
            capabilities_dir=self.capabilities_dir,
            specs_dir=self.specs_dir,
            validate_tools_direct_call_func=self._playbook_installer.validate_tools_direct_call,
        )

    @staticmethod
    def _create_result() -> InstallResult:
        """Create the legacy-compatible install result shape."""
        return InstallResult(
            installed={
                "playbooks": [],
                "tools": [],
                "services": [],
                "api_endpoints": [],
                "schema_modules": [],
                "database_models": [],
                "migrations": [],
                "ui_components": [],
                "bundles": [],
            }
        )

    @staticmethod
    def _coerce_result(result: LegacyResult) -> Tuple[InstallResult, Optional[Dict]]:
        """Normalize legacy dict results to InstallResult while preserving callers."""
        if isinstance(result, InstallResult):
            return result, None
        return InstallResult.from_dict(result), result

    @staticmethod
    def _sync_legacy_result(result: InstallResult, legacy_result: Optional[Dict]) -> None:
        """Write the InstallResult back into a legacy dict when needed."""
        if legacy_result is None:
            return
        legacy_result.clear()
        legacy_result.update(result.to_dict())

    @staticmethod
    def _resolve_manifest_path(temp_dir: Optional[Path], cap_dir: Path) -> Optional[Path]:
        """Resolve the extracted manifest path for both ZIP and tar.gz mindpacks."""
        if temp_dir and (temp_dir / "manifest.yaml").exists():
            return temp_dir / "manifest.yaml"
        if (cap_dir / "manifest.yaml").exists():
            return cap_dir / "manifest.yaml"
        return None

    def install_from_mindpack(
        self, mindpack_path: Path, validate: bool = True
    ) -> Tuple[bool, Dict]:
        """
        Install a capability pack from a .mindpack file.

        Returns:
            Tuple of `(success, result_dict)`.
        """
        result = self._create_result()

        if not mindpack_path.exists():
            result.add_error(f"Mindpack file not found: {mindpack_path}")
            return False, result.to_dict()

        temp_dir: Optional[Path] = None
        try:
            extracted, temp_dir, capability_code, cap_dir = self._extractor.extract(
                mindpack_path
            )
            if not extracted or temp_dir is None or capability_code is None or cap_dir is None:
                result.add_error(f"Failed to extract mindpack: {mindpack_path}")
                return False, result.to_dict()

            result.capability_code = capability_code
            manifest_path = self._resolve_manifest_path(temp_dir, cap_dir)
            if manifest_path is None:
                result.add_error("manifest.yaml not found in mindpack")
                return False, result.to_dict()

            try:
                with open(manifest_path, "r", encoding="utf-8") as file:
                    manifest = yaml.safe_load(file) or {}
            except Exception as exc:
                result.add_error(f"Failed to parse manifest: {exc}")
                return False, result.to_dict()

            if validate:
                logger.info(f"Validating manifest for {capability_code}...")
                is_valid, validation_errors, validation_warnings = self._validate_manifest(
                    manifest_path,
                    cap_dir,
                )
                for warning in validation_warnings:
                    result.add_warning(warning)
                if not is_valid:
                    error_message = f"Manifest validation failed: {validation_errors}"
                    result.add_error(error_message)
                    logger.error(error_message)
                    if self._manifest_validator.should_block_installation(
                        is_valid, validation_errors
                    ):
                        return False, result.to_dict()

            success = self._install_capability(cap_dir, capability_code, manifest, result)
            return success, result.to_dict()
        finally:
            self._extractor.cleanup(temp_dir)

    def _validate_manifest(
        self, manifest_path: Path, cap_dir: Path
    ) -> Tuple[bool, List[str], List[str]]:
        """Validate the extracted manifest through the modular validator."""
        return self._manifest_validator.validate(manifest_path, cap_dir)

    def _install_capability(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: LegacyResult,
    ) -> bool:
        """Install capability assets while keeping the legacy public facade."""
        result_model, legacy_result = self._coerce_result(result)
        try:
            self._install_playbooks(cap_dir, capability_code, manifest, result_model)
            self._install_tools(cap_dir, capability_code, result_model)
            self._install_services(cap_dir, capability_code, result_model)
            self._install_api_endpoints(cap_dir, capability_code, result_model)
            self._install_schema_modules(cap_dir, capability_code, result_model)
            self._install_database_models(cap_dir, capability_code, result_model)
            self._install_migrations(cap_dir, capability_code, result_model)

            if result_model.installed.get("migrations"):
                self._execute_migrations(capability_code, result_model)

            self._install_ui_components(cap_dir, capability_code, manifest, result_model)
            self._install_manifest(cap_dir, capability_code, manifest)
            self._install_root_files(cap_dir, capability_code, result_model)
            self._install_bundles(cap_dir, capability_code, result_model)
            self._reload_capability_registry(capability_code)
            self._check_dependencies(manifest, result_model)
            self._run_post_install_hooks(cap_dir, capability_code, manifest, result_model)
            self._validate_installed_playbooks(
                capability_code,
                manifest,
                result_model,
            )

            if result_model.has_errors():
                logger.error(
                    f"Installation failed due to errors: {result_model.errors}"
                )
                return False

            logger.info(f"Successfully installed capability: {capability_code}")
            return True
        except Exception as exc:
            logger.error(f"Failed to install capability: {exc}")
            result_model.add_error(f"Installation failed: {exc}")
            return False
        finally:
            self._sync_legacy_result(result_model, legacy_result)

    def _reload_capability_registry(self, capability_code: str) -> None:
        """Refresh capability registry caches after asset installation."""
        try:
            from backend.app.services.capability_registry import get_registry

            registry = get_registry()
            if hasattr(registry, "_capabilities_cache"):
                registry._capabilities_cache.clear()
            if hasattr(registry, "_tools_cache"):
                registry._tools_cache.clear()
            registry._load_capability(
                capability_code,
                self.capabilities_dir / capability_code,
            )
            logger.debug(f"Reloaded capability registry for {capability_code}")
        except Exception as exc:
            logger.warning(f"Failed to reload capability registry: {exc}")

    def _validate_installed_playbooks(
        self,
        capability_code: str,
        manifest: Dict,
        result: LegacyResult,
    ) -> None:
        """Run post-install playbook validation via the modular validator."""
        result_model, legacy_result = self._coerce_result(result)
        self._playbook_validator.validate_installed_playbooks(
            capability_code,
            manifest,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _check_dependencies(self, manifest: Dict, result: LegacyResult) -> None:
        """Check dependencies and register degradation status."""
        result_model, legacy_result = self._coerce_result(result)
        capability_code = result_model.capability_code
        if not capability_code:
            self._sync_legacy_result(result_model, legacy_result)
            return

        (
            missing_required,
            missing_optional,
            missing_external,
            missing_system_tools,
            degraded_features_map,
        ) = self._dependency_checker.check_dependencies(manifest, result_model)

        if (
            missing_required
            or missing_optional
            or missing_external
            or missing_system_tools
        ):
            self._degradation_registrar.register_degradation_status(
                capability_code=capability_code,
                manifest=manifest,
                missing_required=missing_required,
                missing_optional=missing_optional
                + missing_external
                + missing_system_tools,
                degraded_features_map=degraded_features_map,
                result=result_model,
            )

        self._sync_legacy_result(result_model, legacy_result)

    def _is_dependency_available(self, dep_name: str) -> bool:
        """Check whether a Python dependency is importable."""
        return self._dependency_checker.is_dependency_available(dep_name)

    def _is_env_var_set(self, env_var: str) -> bool:
        """Check whether an environment variable is present."""
        return self._dependency_checker.is_env_var_set(env_var)

    def _register_degradation_status(
        self,
        capability_code: str,
        manifest: Dict,
        missing_required: List[str],
        missing_optional: List[str],
        degraded_features_map: Dict[str, List[str]],
        result: LegacyResult,
    ) -> None:
        """Delegate degradation registration to the modular registrar."""
        result_model, legacy_result = self._coerce_result(result)
        self._degradation_registrar.register_degradation_status(
            capability_code=capability_code,
            manifest=manifest,
            missing_required=missing_required,
            missing_optional=missing_optional,
            degraded_features_map=degraded_features_map,
            result=result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _install_playbooks(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: LegacyResult,
    ) -> None:
        """Install playbook specs and localized markdown assets."""
        result_model, legacy_result = self._coerce_result(result)
        self._playbook_installer.install_playbooks(
            cap_dir,
            capability_code,
            manifest,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _validate_playbook_required_fields(
        self, spec_path: Path, playbook_code: str
    ) -> List[str]:
        """Validate required fields in a playbook spec."""
        return self._playbook_installer.validate_playbook_required_fields(
            spec_path,
            playbook_code,
        )

    def _validate_tools_direct_call(
        self, playbook_code: str, capability_code: str
    ) -> List[str]:
        """Retain the legacy private method shape for tool-call validation."""
        errors, _warnings = self._playbook_installer.validate_tools_direct_call(
            playbook_code,
            capability_code,
        )
        return errors

    def _install_tools(
        self, cap_dir: Path, capability_code: str, result: LegacyResult
    ) -> None:
        """Install capability tools via the modular runtime assets installer."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_tools(cap_dir, capability_code, result_model)
        self._sync_legacy_result(result_model, legacy_result)

    def _install_services(
        self, cap_dir: Path, capability_code: str, result: LegacyResult
    ) -> None:
        """Install capability services via the modular runtime assets installer."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_services(
            cap_dir,
            capability_code,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _install_api_endpoints(
        self, cap_dir: Path, capability_code: str, result: LegacyResult
    ) -> None:
        """Install capability API or route modules."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_api_endpoints(
            cap_dir,
            capability_code,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _install_schema_modules(
        self, cap_dir: Path, capability_code: str, result: LegacyResult
    ) -> None:
        """Install schema modules and bundled schema data."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_schema_modules(
            cap_dir,
            capability_code,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _install_database_models(
        self, cap_dir: Path, capability_code: str, result: LegacyResult
    ) -> None:
        """Install capability database models."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_database_models(
            cap_dir,
            capability_code,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _install_migrations(
        self, cap_dir: Path, capability_code: str, result: LegacyResult
    ) -> None:
        """Install capability migrations into the Alembic versions directory."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_migrations(
            cap_dir,
            capability_code,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _execute_migrations(self, capability_code: str, result: LegacyResult) -> None:
        """Execute installed migrations for this capability."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.execute_migrations(capability_code, result_model)
        self._sync_legacy_result(result_model, legacy_result)

    def _install_ui_components(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: LegacyResult,
    ) -> None:
        """Install UI components for the capability pack."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_ui_components(
            cap_dir,
            capability_code,
            manifest,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _install_manifest(
        self, cap_dir: Path, capability_code: str, manifest: Dict
    ) -> None:
        """Install the capability manifest into the capability directory."""
        self._runtime_assets_installer.install_manifest(cap_dir, capability_code, manifest)

    def _install_root_files(
        self, cap_dir: Path, capability_code: str, result: LegacyResult
    ) -> None:
        """Install root-level Python, YAML, and Markdown files."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_root_files(
            cap_dir,
            capability_code,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _install_bundles(
        self, cap_dir: Path, capability_code: str, result: LegacyResult
    ) -> None:
        """Install pack-local bundle assets used by local_bundle model manifests."""
        result_model, legacy_result = self._coerce_result(result)
        self._runtime_assets_installer.install_bundles(
            cap_dir,
            capability_code,
            result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _run_post_install_hooks(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: LegacyResult,
    ) -> None:
        """Run manifest-declared post-install hooks and preserve legacy IG fallback."""
        result_model, legacy_result = self._coerce_result(result)
        bootstrap_scripts = manifest.get("bootstrap", [])
        if bootstrap_scripts:
            self._post_install_handler.run_post_install_hooks(
                cap_dir,
                capability_code,
                manifest,
                result_model,
            )
        elif capability_code in _LEGACY_CONTENT_VAULT_CAPABILITIES:
            self._bootstrap_content_vault(result_model)
        self._sync_legacy_result(result_model, legacy_result)

    def _bootstrap_content_vault(
        self, result: LegacyResult, vault_path: Optional[str] = None
    ) -> None:
        """Execute the legacy content-vault bootstrap fallback."""
        result_model, legacy_result = self._coerce_result(result)
        strategy = ContentVaultInitStrategy()
        strategy.execute(
            local_core_root=self.local_core_root,
            cap_dir=self.local_core_root,
            capability_code=result_model.capability_code or "",
            config={"vault_path": vault_path} if vault_path else {},
            result=result_model,
        )
        self._sync_legacy_result(result_model, legacy_result)

    def _run_python_script(self, script_path: Path, result: LegacyResult) -> None:
        """Run a bootstrap Python script while keeping legacy result updates."""
        result_model, legacy_result = self._coerce_result(result)
        logger.info(f"Running bootstrap script: {script_path}")
        process_result = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(self.local_core_root),
            capture_output=True,
            text=True,
            timeout=60,
        )

        if process_result.returncode == 0:
            logger.info(f"Bootstrap script completed: {script_path}")
            result_model.bootstrap.append(str(script_path.name))
        else:
            error_message = process_result.stderr or process_result.stdout
            logger.warning(f"Bootstrap script failed: {error_message}")
            result_model.add_warning(f"Bootstrap script failed: {error_message}")

        self._sync_legacy_result(result_model, legacy_result)
