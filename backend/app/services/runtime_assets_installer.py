"""
Runtime Assets Installer

Install runtime assets and execute capability-specific migrations.
"""

import logging
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
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

logger = logging.getLogger(__name__)

SCRIPT_DIR_EXCLUDES = {
    "__pycache__",
    ".git",
    "node_modules",
    ".mypy_cache",
    ".pytest_cache",
}
SCRIPT_FILE_EXCLUDES = {".DS_Store"}
SCRIPT_SUFFIX_EXCLUDES = {".pyc", ".pyo"}


def _clear_directory_contents(target_dir: Path) -> None:
    """Remove all children from an existing directory without deleting the root."""
    if not target_dir.exists():
        return

    for child in target_dir.iterdir():
        if child.is_symlink() or child.is_file():
            child.unlink()
        else:
            shutil.rmtree(child)


def _safe_asset_segment(value: object, fallback: str) -> str:
    raw = str(value or fallback).strip() or fallback
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_", "."} else "-" for ch in raw)
    return safe.strip(".-") or fallback


def _sha256_integrity(file_path: Path) -> str:
    digest = hashlib.sha256(file_path.read_bytes()).digest()
    return "sha256-" + base64.b64encode(digest).decode("ascii")


class RuntimeAssetsInstaller:
    """Install runtime assets (tools, services, API, schema, models, migrations, UI, manifest, root files, bundles)"""

    def __init__(self, local_core_root: Path, capabilities_dir: Path):
        """
        Initialize installer

        Args:
            local_core_root: Local-core project root directory
            capabilities_dir: Directory for capability manifests
        """
        self.local_core_root = local_core_root
        self.capabilities_dir = capabilities_dir
    def install_all(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult,
        temp_dir: Optional[Path] = None,
    ):
        """
        Install all runtime assets

        Args:
            cap_dir: Extracted capability directory
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: InstallResult to update
            temp_dir: Temporary extraction directory (for ZIP format manifest location)
        """
        # 1. Install scripts
        self.install_scripts(cap_dir, capability_code, result)

        # 2. Install tools
        self.install_tools(cap_dir, capability_code, result)

        # 3. Install services
        self.install_services(cap_dir, capability_code, result)

        # 3b. Install jobs directory
        self.install_jobs(cap_dir, capability_code, result)

        # 4. Install API endpoints
        self.install_api_endpoints(cap_dir, capability_code, result)

        # 5. Install schema modules
        self.install_schema_modules(cap_dir, capability_code, result)

        # 6. Install database models
        self.install_database_models(cap_dir, capability_code, result)

        # 6b. Install capability models (models/ directory)
        self.install_capability_models(cap_dir, capability_code, result)

        # 7. Install migrations directory (copy migrations/ to capability directory)
        self.install_migrations_directory(cap_dir, capability_code, result)

        # 8. Install migrations (copy migration files to alembic/versions/)
        self.install_migrations(cap_dir, capability_code, result)

        # Note: Migration execution is deferred to capability_packs.py install_from_file
        # to ensure migrations run even if playbook validation fails

        # 9. Install UI components
        self.install_ui_components(cap_dir, capability_code, manifest, result)

        # 10. Install manifest
        self.install_manifest(cap_dir, capability_code, manifest, temp_dir)

        # 11. Install root-level Python files and YAML files
        self.install_root_files(cap_dir, capability_code, result)

        # 12. Install pack-local bundles (e.g. local_bundle model assets)
        self.install_bundles(cap_dir, capability_code, result)

        # 13. Install docs directory (agent_guide, etc.)
        self.install_docs(cap_dir, capability_code, result)

        self.install_evals(cap_dir, capability_code, result)

        self.install_workflows(cap_dir, capability_code, result)

    def install_workflows(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install workflows directory (e.g. ComfyUI workflow templates + .meta.json sidecars)"""
        workflows_dir = cap_dir / "workflows"
        if not workflows_dir.exists():
            return

        target_workflows_dir = self.capabilities_dir / capability_code / "workflows"
        if target_workflows_dir.exists():
            shutil.rmtree(target_workflows_dir)
        shutil.copytree(workflows_dir, target_workflows_dir)

        installed = [f.name for f in workflows_dir.iterdir() if f.is_file()]
        result.add_installed("workflows", f"{len(installed)} files")
        logger.info(
            f"Installed workflows directory for {capability_code}: {len(installed)} files"
        )

    def install_scripts(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability scripts as a fully replaced runtime tree."""
        scripts_dir = cap_dir / "scripts"
        if not scripts_dir.exists():
            return

        target_scripts_dir = self.capabilities_dir / capability_code / "scripts"
        if target_scripts_dir.exists():
            shutil.rmtree(target_scripts_dir)
        target_scripts_dir.mkdir(parents=True, exist_ok=True)

        copied_files = 0
        for script_file in sorted(scripts_dir.rglob("*")):
            if not script_file.is_file():
                continue
            if self._should_skip_script_asset(script_file, scripts_dir):
                continue

            relative_path = script_file.relative_to(scripts_dir)
            target_script = target_scripts_dir / relative_path
            target_script.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(script_file, target_script)
            copied_files += 1

            relative_script = relative_path.as_posix()
            if script_file.name != "__init__.py":
                result.add_installed("scripts", relative_script)
            logger.debug(f"Installed script asset: {relative_script}")

        logger.info(
            "Installed scripts directory for %s: %s files",
            capability_code,
            copied_files,
        )

    @staticmethod
    def _should_skip_script_asset(script_file: Path, scripts_dir: Path) -> bool:
        relative_path = script_file.relative_to(scripts_dir)
        if any(part in SCRIPT_DIR_EXCLUDES for part in relative_path.parts[:-1]):
            return True
        if script_file.name in SCRIPT_FILE_EXCLUDES:
            return True
        return script_file.suffix in SCRIPT_SUFFIX_EXCLUDES

    def install_tools(self, cap_dir: Path, capability_code: str, result: InstallResult):
        """Install capability tools as a fully replaced runtime tree."""
        tools_dir = cap_dir / "tools"
        if not tools_dir.exists():
            return

        target_tools_dir = self.capabilities_dir / capability_code / "tools"
        _clear_directory_contents(target_tools_dir)
        target_tools_dir.mkdir(parents=True, exist_ok=True)

        for tool_file in tools_dir.glob("*.py"):
            # Skip __pycache__ but allow __init__.py
            if tool_file.name.startswith("__") and tool_file.name != "__init__.py":
                continue

            target_tool = target_tools_dir / tool_file.name
            shutil.copy2(tool_file, target_tool)
            tool_name = tool_file.stem
            result.add_installed("tools", tool_name)
            logger.debug(f"Installed tool: {tool_name}")

        # Also install tool subdirectories (tool packages).
        # Many capabilities split large tools into packages like tools/foo/*.
        for item in tools_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith("__"):
                # Skip __pycache__ and other dunder dirs
                continue
            target_subdir = target_tools_dir / item.name
            if target_subdir.exists():
                shutil.rmtree(target_subdir)
            shutil.copytree(item, target_subdir)
            logger.debug(f"Installed tools subdirectory: {item.name}")
            result.add_installed("tools_dirs", item.name)

    def install_services(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability services as a fully replaced runtime tree."""
        services_dir = cap_dir / "services"
        if not services_dir.exists():
            return

        target_services_dir = self.capabilities_dir / capability_code / "services"
        _clear_directory_contents(target_services_dir)
        target_services_dir.mkdir(parents=True, exist_ok=True)

        for service_file in services_dir.glob("*.py"):
            if service_file.name.startswith("__") and service_file.name != "__init__.py":
                continue

            target_service = target_services_dir / service_file.name
            shutil.copy2(service_file, target_service)
            service_name = service_file.stem
            if service_name != "__init__":
                result.add_installed("services", service_name)
            logger.debug(f"Installed service: {service_name}")

        # Also install service subdirectories (service packages).
        for item in services_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith("__"):
                continue
            target_subdir = target_services_dir / item.name
            if target_subdir.exists():
                shutil.rmtree(target_subdir)
            shutil.copytree(item, target_subdir)
            logger.debug(f"Installed services subdirectory: {item.name}")
            result.add_installed("service_dirs", item.name)

    def install_jobs(self, cap_dir: Path, capability_code: str, result: InstallResult):
        """Install capability jobs directory"""
        jobs_dir = cap_dir / "jobs"
        if not jobs_dir.exists():
            return

        target_jobs_dir = self.capabilities_dir / capability_code / "jobs"
        target_jobs_dir.mkdir(parents=True, exist_ok=True)

        for job_file in jobs_dir.glob("*.py"):
            target_job = target_jobs_dir / job_file.name
            shutil.copy2(job_file, target_job)
            job_name = job_file.stem
            if not job_name.startswith("__"):
                result.add_installed("jobs", job_name)
            logger.debug(f"Installed job: {job_file.name}")

        for item in jobs_dir.iterdir():
            if item.is_dir() and not item.name.startswith("__"):
                target_subdir = target_jobs_dir / item.name
                if target_subdir.exists():
                    shutil.rmtree(target_subdir)
                shutil.copytree(item, target_subdir)
                logger.debug(f"Installed jobs subdirectory: {item.name}")
                result.add_installed("jobs_dirs", item.name)

    def install_api_endpoints(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability API endpoints from 'api' or 'routes' directory"""
        api_dir = cap_dir / "api"
        routes_dir = cap_dir / "routes"

        # Install from 'api' directory if exists
        if api_dir.exists():
            target_api_dir = self.capabilities_dir / capability_code / "api"
            target_api_dir.mkdir(parents=True, exist_ok=True)

            for item in api_dir.iterdir():
                if not item.is_dir() or item.name == "__pycache__":
                    continue
                target_subdir = target_api_dir / item.name
                if target_subdir.exists():
                    shutil.rmtree(target_subdir)
                shutil.copytree(
                    item,
                    target_subdir,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
                result.add_installed("api_dirs", item.name)
                logger.debug(f"Installed API package directory: {item.name}")

            for api_file in api_dir.glob("*.py"):
                target_api = target_api_dir / api_file.name
                shutil.copy2(api_file, target_api)
                # Only track non-__init__ files in installed list
                if not api_file.name.startswith("__"):
                    api_name = api_file.stem
                    result.add_installed("api_endpoints", api_name)
                    logger.debug(f"Installed API endpoint: {api_name}")
                else:
                    logger.debug(f"Installed API file: {api_file.name}")

        # Also install from 'routes' directory if exists
        if routes_dir.exists():
            target_routes_dir = self.capabilities_dir / capability_code / "routes"
            target_routes_dir.mkdir(parents=True, exist_ok=True)

            for item in routes_dir.iterdir():
                if not item.is_dir() or item.name == "__pycache__":
                    continue
                target_subdir = target_routes_dir / item.name
                if target_subdir.exists():
                    shutil.rmtree(target_subdir)
                shutil.copytree(
                    item,
                    target_subdir,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
                )
                result.add_installed("api_dirs", item.name)
                logger.debug(f"Installed route package directory: {item.name}")

            for route_file in routes_dir.glob("*.py"):
                target_route = target_routes_dir / route_file.name
                shutil.copy2(route_file, target_route)
                # Only track non-__init__ files in installed list
                if not route_file.name.startswith("__"):
                    route_name = route_file.stem
                    result.add_installed("api_endpoints", route_name)
                    logger.debug(f"Installed route: {route_name}")
                else:
                    logger.debug(f"Installed route file: {route_file.name}")

    def install_schema_modules(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability schema modules and data directories"""
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
                result.add_installed("schema_modules", schema_name)
            logger.debug(f"Installed schema module: {schema_file.name}")

        # Install all subdirectories (e.g., schema/rubrics/, schema/data/)
        # This includes runtime data files that need to be available at runtime
        for item in schema_dir.iterdir():
            if item.is_dir() and not item.name.startswith("__"):
                target_subdir = target_schema_dir / item.name
                if target_subdir.exists():
                    # Remove existing directory to ensure clean copy
                    shutil.rmtree(target_subdir)
                shutil.copytree(item, target_subdir)
                logger.debug(f"Installed schema subdirectory: {item.name}")
                result.add_installed("schema_data_dirs", item.name)

    def install_database_models(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability database models"""
        database_models_dir = cap_dir / "database" / "models"
        if not database_models_dir.exists():
            return

        # Target: app/models/{capability_code}/
        target_models_dir = self.local_core_root / "backend" / "app" / "models"
        target_models_dir.mkdir(parents=True, exist_ok=True)

        # Install all Python files from database/models/
        for model_file in database_models_dir.glob("*.py"):
            if model_file.name.startswith("__"):
                continue

            # Install as app/models/{capability_code}/{model_file.name}
            target_model_dir = target_models_dir / capability_code
            target_model_dir.mkdir(parents=True, exist_ok=True)

            target_model = target_model_dir / model_file.name

            # Read and fix import paths for local-core
            # Try multiple encodings to handle different file encodings
            content = None
            for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
                try:
                    with open(model_file, "r", encoding=encoding) as f:
                        content = f.read()
                    break
                except UnicodeDecodeError:
                    continue

            if content is None:
                # If all encodings fail, try binary read and decode with errors='replace'
                with open(model_file, "rb") as f:
                    raw_content = f.read()
                content = raw_content.decode("utf-8", errors="replace")

            # Fix Base import: from .. import Base -> from database import Base
            if "from .. import Base" in content:
                content = content.replace(
                    "from .. import Base", "from database import Base"
                )

            with open(target_model, "w", encoding="utf-8") as f:
                f.write(content)

            model_name = model_file.stem
            result.add_installed("database_models", model_name)
            logger.debug(f"Installed database model: {model_file.name} (imports fixed)")

        # Install __init__.py if exists
        init_file = database_models_dir / "__init__.py"
        if init_file.exists():
            target_init_dir = target_models_dir / capability_code
            target_init_dir.mkdir(parents=True, exist_ok=True)
            target_init = target_init_dir / "__init__.py"
            shutil.copy2(init_file, target_init)
            logger.debug(f"Installed database models __init__.py")

    def install_capability_models(
        self, cap_dir: Path, capability_code: str, result: InstallResult
    ):
        """Install capability models from models/ directory to app/capabilities/{capability_code}/models/"""
        models_dir = cap_dir / "models"
        if not models_dir.exists():
            return

        # Target: app/capabilities/{capability_code}/models/
        target_models_dir = self.capabilities_dir / capability_code / "models"
        target_models_dir.mkdir(parents=True, exist_ok=True)

        # models/ can contain runtime data assets such as JSON vocabularies in
        # addition to Python modules, so copy all files except cache artifacts.
        for model_file in models_dir.rglob("*"):
            if not model_file.is_file():
                continue
            if "__pycache__" in model_file.parts:
                continue

            # Calculate relative path from models_dir to preserve subdirectory structure
            relative_path = model_file.relative_to(models_dir)
            target_model = target_models_dir / relative_path

            # Create parent directories if needed
            target_model.parent.mkdir(parents=True, exist_ok=True)

            shutil.copy2(model_file, target_model)
            if not model_file.name.startswith("__"):
                result.add_installed("capability_models", str(relative_path))
            logger.debug(f"Installed capability model asset: {relative_path}")

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
            import shutil

            shutil.rmtree(target_migrations_dir)

        import shutil

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

    def install_ui_components(
        self, cap_dir: Path, capability_code: str, manifest: Dict, result: InstallResult
    ):
        """
        Install compiled UI assets without mutating the frontend source tree.

        Args:
            cap_dir: Extracted capability directory (from .mindpack)
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: InstallResult to update
        """
        ui_components = manifest.get("ui_components", [])
        if not ui_components:
            return

        source_ui_dist_dir = cap_dir / "ui_dist"
        if not source_ui_dist_dir.exists():
            if (cap_dir / "ui").exists():
                result.add_warning(
                    f"UI source for {capability_code} was not installed; pack must include compiled ui_dist assets."
                )
            return

        dist_manifest_path = source_ui_dist_dir / "ui_dist_manifest.json"
        if not dist_manifest_path.exists():
            result.add_warning(
                f"Compiled UI assets for {capability_code} missing ui_dist_manifest.json"
            )
            return

        try:
            dist_manifest = json.loads(dist_manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            result.add_warning(f"Failed to parse ui_dist_manifest.json: {exc}")
            return

        version_segment = _safe_asset_segment(manifest.get("version"), "unversioned")
        assets_root = Path(
            os.getenv(
                "MINDSCAPE_CAPABILITY_UI_ASSETS_DIR",
                str(self.local_core_root / "data" / "capability-ui"),
            )
        )
        target_assets_dir = assets_root / capability_code / version_segment
        if target_assets_dir.exists():
            shutil.rmtree(target_assets_dir)
        target_assets_dir.mkdir(parents=True, exist_ok=True)

        runtime_components = []
        for component in dist_manifest.get("components", []):
            component_code = component.get("code")
            asset_path = str(component.get("asset_path") or "").strip()
            if not component_code or not asset_path:
                continue
            source_asset = (source_ui_dist_dir / asset_path).resolve()
            try:
                source_asset.relative_to(source_ui_dist_dir.resolve())
            except ValueError:
                result.add_warning(f"Skipping unsafe UI asset path: {asset_path}")
                continue
            if not source_asset.exists() or not source_asset.is_file():
                result.add_warning(f"Compiled UI asset not found: {asset_path}")
                continue

            target_asset = target_assets_dir / asset_path
            target_asset.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source_asset, target_asset)
            integrity = component.get("integrity") or _sha256_integrity(target_asset)
            runtime_components.append(
                {
                    "code": component_code,
                    "asset_path": f"{version_segment}/{asset_path}",
                    "asset_url": (
                        f"/api/v1/capability-packs/installed-capabilities/"
                        f"{capability_code}/ui-assets/{version_segment}/{asset_path}"
                    ),
                    "integrity": integrity,
                    "bytes": target_asset.stat().st_size,
                    "export": component.get("export", "default"),
                    "runtime": component.get("runtime", "mindscape-react-bridge-v1"),
                }
            )
            result.add_installed("ui_components", str(component_code))

        if not runtime_components:
            return

        target_cap_dir = self.capabilities_dir / capability_code
        target_cap_dir.mkdir(parents=True, exist_ok=True)
        sidecar_path = target_cap_dir / "ui_runtime_assets.json"
        sidecar_path.write_text(
            json.dumps(
                {
                    "capability_code": capability_code,
                    "version": version_segment,
                    "components": runtime_components,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        logger.info(
            "Installed compiled UI runtime assets for %s: %s components",
            capability_code,
            len(runtime_components),
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

        Args:
            cap_dir: Extracted capability directory
            capability_code: Capability code
            manifest: Parsed manifest dict
            temp_dir: Temporary extraction directory (for ZIP format manifest location)
        """
        target_cap_dir = self.capabilities_dir / capability_code
        target_cap_dir.mkdir(parents=True, exist_ok=True)

        # Find manifest.yaml (ZIP root or capability dir)
        manifest_path = None
        if temp_dir and (temp_dir / "manifest.yaml").exists():
            # ZIP format: manifest at ZIP root
            manifest_path = temp_dir / "manifest.yaml"
        elif (cap_dir / "manifest.yaml").exists():
            # tar.gz format: manifest in capability directory
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

        # Install all .py files in capability root directory
        for py_file in cap_dir.glob("*.py"):
            if py_file.is_file():
                target_file = cap_install_dir / py_file.name
                shutil.copy2(py_file, target_file)
                logger.debug(f"Installed root file: {py_file.name}")
                result.add_installed("root_files", py_file.name)

        # Install all .yaml files in capability root directory (e.g., migrations.yaml)
        for yaml_file in cap_dir.glob("*.yaml"):
            if yaml_file.is_file() and yaml_file.name != "manifest.yaml":
                target_file = cap_install_dir / yaml_file.name
                shutil.copy2(yaml_file, target_file)
                logger.debug(f"Installed root YAML file: {yaml_file.name}")
                result.add_installed("root_files", yaml_file.name)

        # Install all .md files in capability root directory (e.g., SKILL.md)
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
