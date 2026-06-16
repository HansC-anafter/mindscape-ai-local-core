"""Runtime asset delegates for the deprecated capability installer."""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict

from .capability_installer_result import LegacyResult

logger = logging.getLogger(__name__)


class CapabilityInstallerRuntimeAssetsMixin:
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
