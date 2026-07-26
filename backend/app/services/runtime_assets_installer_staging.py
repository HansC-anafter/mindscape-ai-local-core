import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import Dict, Optional

from backend.app.routes.core.capability_install_core.install_commit_core.filesystem_saga import (
    PreparedCapabilityTree,
)

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
        install_id: Optional[str] = None,
    ):
        """Reject the former second publish path outside install coordinator."""
        raise RuntimeError("runtime_assets_install_all_requires_install_commit_coordinator")

    def prepare_staged_tree(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult,
        temp_dir: Optional[Path] = None,
        *,
        install_id: Optional[str] = None,
    ) -> PreparedCapabilityTree:
        target_cap_dir = self.capabilities_dir / capability_code
        normalized_install_id = str(install_id or "").strip() or uuid.uuid4().hex
        staging_root = _build_staging_root(
            capability_code,
            install_id=normalized_install_id,
            capabilities_dir=self.capabilities_dir,
        )
        staging_capabilities_dir = staging_root
        staging_cap_dir = staging_root / capability_code
        previous_root = (
            self.capabilities_dir.parent
            / ".capability-install-previous"
            / normalized_install_id
        )
        previous_cap_dir = previous_root / capability_code

        try:
            if staging_root.exists():
                raise RuntimeError(
                    f"Capability install staging already exists for {normalized_install_id}"
                )
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
            self._assert_same_publish_device(
                staging_cap_dir=staging_cap_dir,
                target_cap_dir=target_cap_dir,
            )
            prepared = PreparedCapabilityTree(
                install_id=normalized_install_id,
                capability_code=capability_code,
                staging_root=staging_root,
                staging_cap_dir=staging_cap_dir,
                target_cap_dir=target_cap_dir,
                previous_root=previous_root,
                previous_cap_dir=previous_cap_dir,
            )
            self.prepare_host_assets(
                cap_dir=cap_dir,
                manifest=manifest,
                prepared=prepared,
                result=result,
            )
            return prepared
        except Exception:
            if staging_root.exists():
                shutil.rmtree(staging_root, ignore_errors=True)
            raise

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

    @staticmethod
    def _assert_same_publish_device(
        *,
        staging_cap_dir: Path,
        target_cap_dir: Path,
    ) -> None:
        target_cap_dir.parent.mkdir(parents=True, exist_ok=True)
        staging_device = os.stat(staging_cap_dir).st_dev
        target_device = os.stat(target_cap_dir.parent).st_dev
        if staging_device != target_device:
            raise OSError(
                f"Capability candidate and live target are on different filesystems: "
                f"candidate_device={staging_device} target_device={target_device}"
            )

    def publish_candidate_retaining_previous(
        self,
        prepared: PreparedCapabilityTree,
    ) -> PreparedCapabilityTree:
        if prepared.finalized:
            raise RuntimeError("capability_publish_already_finalized")
        if prepared.published:
            return prepared
        self._assert_same_publish_device(
            staging_cap_dir=prepared.staging_cap_dir,
            target_cap_dir=prepared.target_cap_dir,
        )
        publish_parent = prepared.target_cap_dir.parent
        publish_parent.mkdir(parents=True, exist_ok=True)
        prepared.previous_root.mkdir(parents=True, exist_ok=True)
        if prepared.previous_cap_dir.exists():
            raise RuntimeError("capability_previous_tree_already_exists")

        moved_existing = False
        try:
            if prepared.target_cap_dir.exists():
                prepared.target_cap_dir.rename(prepared.previous_cap_dir)
                moved_existing = True
            prepared.staging_cap_dir.rename(prepared.target_cap_dir)
            self.publish_host_assets(prepared)
            prepared.published = True
            return prepared
        except Exception:
            if (
                prepared.target_cap_dir.exists()
                and not prepared.staging_cap_dir.exists()
            ):
                prepared.target_cap_dir.rename(prepared.staging_cap_dir)
            if moved_existing and prepared.previous_cap_dir.exists():
                prepared.previous_cap_dir.rename(prepared.target_cap_dir)
            self.restore_host_assets(prepared)
            raise

    def restore_previous(
        self,
        prepared: PreparedCapabilityTree,
    ) -> PreparedCapabilityTree:
        if prepared.finalized or not prepared.published:
            return prepared
        prepared.staging_root.mkdir(parents=True, exist_ok=True)
        if prepared.staging_cap_dir.exists():
            raise RuntimeError("capability_candidate_staging_restore_conflict")
        if prepared.target_cap_dir.exists():
            prepared.target_cap_dir.rename(prepared.staging_cap_dir)
        self.restore_host_assets(prepared)
        if prepared.previous_cap_dir.exists():
            prepared.previous_cap_dir.rename(prepared.target_cap_dir)
        prepared.published = False
        return prepared

    def finalize_publish(
        self,
        prepared: PreparedCapabilityTree,
    ) -> PreparedCapabilityTree:
        if prepared.finalized:
            return prepared
        if not prepared.published:
            raise RuntimeError("capability_candidate_not_published")
        if prepared.previous_root.exists():
            shutil.rmtree(prepared.previous_root)
        if prepared.staging_root.exists():
            shutil.rmtree(prepared.staging_root)
        self.finalize_host_assets(prepared)
        for parent in (prepared.previous_root.parent, prepared.staging_root.parent):
            try:
                parent.rmdir()
            except OSError:
                pass
        prepared.finalized = True
        return prepared

    def _publish_staged_capability_tree(
        self,
        *,
        staging_cap_dir: Path,
        target_cap_dir: Path,
        capability_code: str,
    ) -> None:
        """Legacy leaf helper retained only for isolated compatibility tests."""

        staging_root = staging_cap_dir.parent
        prepared = PreparedCapabilityTree(
            install_id=staging_root.name,
            capability_code=capability_code,
            staging_root=staging_root,
            staging_cap_dir=staging_cap_dir,
            target_cap_dir=target_cap_dir,
            previous_root=target_cap_dir.parent.parent
            / ".capability-install-previous"
            / staging_root.name,
            previous_cap_dir=target_cap_dir.parent.parent
            / ".capability-install-previous"
            / staging_root.name
            / capability_code,
        )
        self.publish_candidate_retaining_previous(prepared)
        self.finalize_publish(prepared)
