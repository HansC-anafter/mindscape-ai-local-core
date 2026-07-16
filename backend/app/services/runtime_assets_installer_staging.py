import errno
import logging
import shutil
import uuid
from pathlib import Path
from typing import Dict, Optional

from .install_result import InstallResult
from .runtime_assets_installer_support import (
    RUNTIME_MIRROR_DIRS,
    _build_staging_root,
    _iter_runtime_mirror_files,
    _sha256_integrity,
)

logger = logging.getLogger("app.services.runtime_assets_installer")


class RuntimeAssetsInstallerStagingMixin:
    def install_all(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult,
        temp_dir: Optional[Path] = None,
    ):
        target_cap_dir = self.capabilities_dir / capability_code
        staging_root = _build_staging_root(
            capability_code,
            local_core_root=self.local_core_root,
        )
        staging_capabilities_dir = staging_root / "capabilities"
        staging_cap_dir = staging_capabilities_dir / capability_code

        try:
            staging_capabilities_dir.mkdir(parents=True, exist_ok=True)
            if target_cap_dir.exists():
                shutil.copytree(
                    target_cap_dir,
                    staging_cap_dir,
                    symlinks=True,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
                )
            else:
                staging_cap_dir.mkdir(parents=True, exist_ok=True)

            original_capabilities_dir = self.capabilities_dir
            self.capabilities_dir = staging_capabilities_dir
            try:
                self._install_all_into_current_capabilities(
                    cap_dir=cap_dir,
                    capability_code=capability_code,
                    manifest=manifest,
                    result=result,
                    temp_dir=temp_dir,
                )
            finally:
                self.capabilities_dir = original_capabilities_dir

            self._prune_staged_stale_files(
                staging_cap_dir=staging_cap_dir,
                incoming_cap_dir=cap_dir,
                capability_code=capability_code,
                result=result,
            )
            self._verify_staged_runtime_tree(
                incoming_cap_dir=cap_dir,
                staging_cap_dir=staging_cap_dir,
                capability_code=capability_code,
            )
            self._publish_staged_capability_tree(
                staging_cap_dir=staging_cap_dir,
                target_cap_dir=target_cap_dir,
                capability_code=capability_code,
            )
        finally:
            if staging_root.exists():
                shutil.rmtree(staging_root, ignore_errors=True)
            staging_parent = staging_root.parent
            try:
                staging_parent.rmdir()
            except OSError:
                pass

    def _install_all_into_current_capabilities(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult,
        temp_dir: Optional[Path] = None,
    ):
        """Install runtime assets into ``self.capabilities_dir``."""
        self.install_scripts(cap_dir, capability_code, result)
        self.install_tools(cap_dir, capability_code, result)
        self.install_services(cap_dir, capability_code, result)
        self.install_runtime_namespace_dirs(cap_dir, capability_code, result)
        self.install_jobs(cap_dir, capability_code, result)
        self.install_api_endpoints(cap_dir, capability_code, result)
        self.install_schema_modules(cap_dir, capability_code, result)
        self.install_database_models(cap_dir, capability_code, result)
        self.install_capability_models(cap_dir, capability_code, result)
        self.install_migrations_directory(cap_dir, capability_code, result)
        self.install_migrations(cap_dir, capability_code, result)
        # Migration execution is deferred to capability_packs.py install_from_file.
        self.install_ui_components(cap_dir, capability_code, manifest, result)
        self.install_manifest(cap_dir, capability_code, manifest, temp_dir)
        self.install_root_files(cap_dir, capability_code, result)
        self.install_bundles(cap_dir, capability_code, result)
        self.install_docs(cap_dir, capability_code, result)
        self.install_evals(cap_dir, capability_code, result)

    def _prune_staged_stale_files(
        self,
        *,
        staging_cap_dir: Path,
        incoming_cap_dir: Path,
        capability_code: str,
        result: InstallResult,
    ) -> None:
        try:
            from app.services.install_integrity import prune_stale_installed_files

            pruned_files = prune_stale_installed_files(
                staging_cap_dir,
                incoming_cap_dir,
            )
            if pruned_files:
                result.add_warning(
                    f"Pruned {len(pruned_files)} stale managed file(s) from {capability_code}."
                )
        except Exception as exc:
            logger.warning(
                "Failed to prune stale staged files for %s: %s",
                capability_code,
                exc,
            )
            result.add_warning(f"Failed to prune stale staged files: {exc}")

    def _verify_staged_runtime_tree(
        self,
        *,
        incoming_cap_dir: Path,
        staging_cap_dir: Path,
        capability_code: str,
    ) -> None:
        missing: list[str] = []
        mismatched: list[str] = []

        for dirname in sorted(RUNTIME_MIRROR_DIRS):
            source_dir = incoming_cap_dir / dirname
            if not source_dir.exists():
                continue
            target_dir = staging_cap_dir / dirname
            if not target_dir.exists():
                missing.append(f"{dirname}/")
                continue
            for relative_path, source_file in _iter_runtime_mirror_files(source_dir):
                target_file = target_dir / relative_path
                display_path = f"{dirname}/{relative_path.as_posix()}"
                if not target_file.exists() or not target_file.is_file():
                    missing.append(display_path)
                    continue
                if _sha256_integrity(source_file) != _sha256_integrity(target_file):
                    mismatched.append(display_path)

        manifest_path = staging_cap_dir / "manifest.yaml"
        if not manifest_path.exists():
            missing.append("manifest.yaml")

        if missing or mismatched:
            missing_sample = ", ".join(missing[:10])
            mismatched_sample = ", ".join(mismatched[:10])
            raise RuntimeError(
                f"Incomplete runtime asset install for {capability_code}: "
                f"missing=[{missing_sample}] mismatched=[{mismatched_sample}]"
            )

    def _publish_staged_capability_tree(
        self,
        *,
        staging_cap_dir: Path,
        target_cap_dir: Path,
        capability_code: str,
    ) -> None:
        publish_parent = target_cap_dir.parent
        publish_parent.mkdir(parents=True, exist_ok=True)
        backup_dir = publish_parent / f".{capability_code}.previous-{uuid.uuid4().hex}"

        moved_existing = False
        try:
            if target_cap_dir.exists():
                target_cap_dir.rename(backup_dir)
                moved_existing = True
            try:
                staging_cap_dir.rename(target_cap_dir)
            except OSError as exc:
                if exc.errno != errno.EXDEV:
                    raise
                shutil.copytree(staging_cap_dir, target_cap_dir, symlinks=True)
                shutil.rmtree(staging_cap_dir, ignore_errors=True)
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
        except Exception:
            if not target_cap_dir.exists() and moved_existing and backup_dir.exists():
                backup_dir.rename(target_cap_dir)
            raise
