import logging
import shutil
from pathlib import Path
from typing import Dict, Optional

from .install_result import InstallResult
from .runtime_assets_installer_core import (
    execute_migrations,
    extract_branch_labels,
    extract_down_revision,
    extract_revision_id,
    install_migrations,
    pack_has_branch_label,
)
from .runtime_assets_installer_support import _clear_directory_contents

logger = logging.getLogger("app.services.runtime_assets_installer")


class RuntimeAssetsInstallerMetadataAssetsMixin:
    def install_migrations_directory(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install migrations directory to capability directory (for execute_migrations to find migrations.yaml)"""
        migrations_dir = cap_dir / "migrations"
        if not migrations_dir.exists():
            return

        target_cap_dir = self.capabilities_dir / capability_code
        target_migrations_dir = target_cap_dir / "migrations"

        if target_migrations_dir.exists():
            shutil.rmtree(target_migrations_dir)

        shutil.copytree(migrations_dir, target_migrations_dir)
        logger.info(f"Installed migrations directory for {capability_code}")

    def install_migrations(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability migration files to the Alembic versions directory."""
        install_migrations(
            cap_dir=cap_dir,
            capability_code=capability_code,
            local_core_root=self.local_core_root,
            result=result,
        )

    @staticmethod
    def _extract_branch_labels(migration_file: Path) -> tuple:
        """Extract branch_labels from a migration file."""
        return extract_branch_labels(migration_file)

    @staticmethod
    def _extract_revision_id(migration_file: Path) -> Optional[str]:
        """Extract the authoritative Alembic revision id from a migration file."""
        return extract_revision_id(migration_file)

    @staticmethod
    def _extract_down_revision(migration_file: Path) -> Optional[str]:
        """Extract the Alembic down_revision from a migration file."""
        return extract_down_revision(migration_file)

    def _pack_has_branch_label(
        self, capability_code: str, alembic_versions_dir: Path
    ) -> bool:
        """Check whether installed migrations declare the capability branch label."""
        return pack_has_branch_label(capability_code, alembic_versions_dir)

    def execute_migrations(self, capability_code: str, result: InstallResult):
        """Execute database migrations for a specific capability only."""
        execute_migrations(
            local_core_root=self.local_core_root,
            capabilities_dir=self.capabilities_dir,
            capability_code=capability_code,
            result=result,
        )

    def install_manifest(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        temp_dir: Optional[Path] = None,
    ):
        """
        Install capability manifest

        Hard contract: Manifest must be in both locations
        - ZIP root: temp_dir/manifest.yaml (for ZIP format)
        - Capability dir: cap_dir/manifest.yaml (for tar.gz format)
        """
        target_cap_dir = self.capabilities_dir / capability_code
        target_cap_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = None
        if temp_dir and (temp_dir / "manifest.yaml").exists():
            manifest_path = temp_dir / "manifest.yaml"
        elif (cap_dir / "manifest.yaml").exists():
            manifest_path = cap_dir / "manifest.yaml"
        else:
            logger.warning(
                f"manifest.yaml not found in expected locations for {capability_code}"
            )
            return

        target_manifest = target_cap_dir / "manifest.yaml"
        shutil.copy2(manifest_path, target_manifest)
        logger.debug(f"Installed manifest: {capability_code}/manifest.yaml")

    def install_root_files(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install root-level Python files and YAML files (e.g., models.py, migrations.yaml)"""
        cap_install_dir = self.capabilities_dir / capability_code
        cap_install_dir.mkdir(parents=True, exist_ok=True)

        for py_file in cap_dir.glob("*.py"):
            if py_file.is_file():
                target_file = cap_install_dir / py_file.name
                shutil.copy2(py_file, target_file)
                logger.debug(f"Installed root file: {py_file.name}")
                result.add_installed("root_files", py_file.name)

        for yaml_file in cap_dir.glob("*.yaml"):
            if yaml_file.is_file() and yaml_file.name != "manifest.yaml":
                target_file = cap_install_dir / yaml_file.name
                shutil.copy2(yaml_file, target_file)
                logger.debug(f"Installed root YAML file: {yaml_file.name}")
                result.add_installed("root_files", yaml_file.name)

        for md_file in cap_dir.glob("*.md"):
            if md_file.is_file():
                target_file = cap_install_dir / md_file.name
                shutil.copy2(md_file, target_file)
                logger.debug(f"Installed root MD file: {md_file.name}")
                result.add_installed("root_files", md_file.name)

    def install_bundles(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install pack-local bundles consumed by model-manifest local_bundle entries."""
        bundles_dir = cap_dir / "bundles"
        if not bundles_dir.exists():
            return

        target_bundles_dir = self.capabilities_dir / capability_code / "bundles"
        if target_bundles_dir.exists() or target_bundles_dir.is_symlink():
            if target_bundles_dir.is_symlink() or target_bundles_dir.is_file():
                target_bundles_dir.unlink()
            else:
                shutil.rmtree(target_bundles_dir)

        shutil.copytree(bundles_dir, target_bundles_dir)

        installed_bundle_files = [
            str(file_path.relative_to(bundles_dir))
            for file_path in bundles_dir.rglob("*")
            if file_path.is_file()
        ]
        result.extend_installed("bundles", installed_bundle_files)
        logger.info(
            "Installed bundles directory for %s: %s files",
            capability_code,
            len(installed_bundle_files),
        )

    def install_docs(self, cap_dir: Path, capability_code: str, result: InstallResult):
        """Install docs directory (contains agent_guide.md etc.)"""
        docs_dir = cap_dir / "docs"
        if not docs_dir.exists():
            return

        target_docs_dir = self.capabilities_dir / capability_code / "docs"
        if target_docs_dir.exists():
            _clear_directory_contents(target_docs_dir)
        else:
            target_docs_dir.mkdir(parents=True, exist_ok=True)

        for doc_file in docs_dir.rglob("*"):
            if doc_file.is_file():
                rel = doc_file.relative_to(docs_dir)
                target = target_docs_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(doc_file, target)
                result.add_installed("docs", str(rel))
                logger.debug(f"Installed doc: {rel}")

    def install_evals(self, cap_dir: Path, capability_code: str, result: InstallResult):
        """Install evals directory (evaluation scenarios and validators)"""
        evals_dir = cap_dir / "evals"
        if not evals_dir.exists():
            return

        target_evals_dir = self.capabilities_dir / capability_code / "evals"
        if target_evals_dir.exists():
            _clear_directory_contents(target_evals_dir)
        else:
            target_evals_dir.mkdir(parents=True, exist_ok=True)

        for eval_file in evals_dir.rglob("*"):
            if eval_file.is_file():
                rel = eval_file.relative_to(evals_dir)
                target = target_evals_dir / rel
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(eval_file, target)
                result.add_installed("evals", str(rel))
                logger.debug(f"Installed eval: {rel}")
