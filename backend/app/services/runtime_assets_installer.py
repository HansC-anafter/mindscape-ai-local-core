"""
Runtime Assets Installer

安装 tools/services/api/schema/database_models/migrations/UI/manifest/root files，执行迁移。
"""

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Dict, Optional

from .install_result import InstallResult

logger = logging.getLogger(__name__)


class RuntimeAssetsInstaller:
    """Install runtime assets (tools, services, API, schema, models, migrations, UI, manifest, root files)"""

    def __init__(
        self,
        local_core_root: Path,
        capabilities_dir: Path
    ):
        """
        Initialize installer

        Args:
            local_core_root: Local-core project root directory
            capabilities_dir: Directory for capability manifests
        """
        self.local_core_root = local_core_root
        self.capabilities_dir = capabilities_dir
        self._cloud_web_console_path = None

    def install_all(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult,
        temp_dir: Optional[Path] = None
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
        # 1. Install tools
        self.install_tools(cap_dir, capability_code, result)

        # 2. Install services
        self.install_services(cap_dir, capability_code, result)

        # 3. Install API endpoints
        self.install_api_endpoints(cap_dir, capability_code, result)

        # 4. Install schema modules
        self.install_schema_modules(cap_dir, capability_code, result)

        # 5. Install database models
        self.install_database_models(cap_dir, capability_code, result)

        # 5b. Install capability models (models/ directory)
        self.install_capability_models(cap_dir, capability_code, result)

        # 6. Install migrations
        self.install_migrations(cap_dir, capability_code, result)

        # 7. Execute migrations if any were installed
        if result.installed.get("migrations"):
            self.execute_migrations(capability_code, result)

        # 8. Install UI components
        self.install_ui_components(cap_dir, capability_code, manifest, result)

        # 9. Install manifest
        self.install_manifest(cap_dir, capability_code, manifest, temp_dir)

        # 10. Install root-level Python files
        self.install_root_files(cap_dir, capability_code, result)

    def install_tools(
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
    ):
        """Install capability tools"""
        tools_dir = cap_dir / "tools"
        if not tools_dir.exists():
            return

        target_tools_dir = self.capabilities_dir / capability_code / "tools"
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

    def install_services(
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
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
            result.add_installed("services", service_name)
            logger.debug(f"Installed service: {service_name}")

    def install_api_endpoints(
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
    ):
        """Install capability API endpoints from 'api' or 'routes' directory"""
        api_dir = cap_dir / "api"
        routes_dir = cap_dir / "routes"

        # Install from 'api' directory if exists
        if api_dir.exists():
            target_api_dir = self.capabilities_dir / capability_code / "api"
            target_api_dir.mkdir(parents=True, exist_ok=True)

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
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
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
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
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

            # Fix Base import: from .. import Base -> from database import Base
            if 'from .. import Base' in content:
                content = content.replace('from .. import Base', 'from database import Base')

            with open(target_model, 'w', encoding='utf-8') as f:
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
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
    ):
        """Install capability models from models/ directory to app/capabilities/{capability_code}/models/"""
        models_dir = cap_dir / "models"
        if not models_dir.exists():
            return

        # Target: app/capabilities/{capability_code}/models/
        target_models_dir = self.capabilities_dir / capability_code / "models"
        target_models_dir.mkdir(parents=True, exist_ok=True)

        # Install all Python files from models/ directory
        for model_file in models_dir.glob("*.py"):
            target_model = target_models_dir / model_file.name
            shutil.copy2(model_file, target_model)
            model_name = model_file.stem
            if not model_name.startswith("__"):
                result.add_installed("capability_models", model_name)
            logger.debug(f"Installed capability model: {model_file.name}")

    def install_migrations(
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
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

        # If no migrations directory and no migrations.yaml, skip
        if not migrations_dir.exists():
            return

        # Target: alembic/postgres/versions/
        alembic_versions_dir = self.local_core_root / "backend" / "alembic" / "postgres" / "versions"
        if not alembic_versions_dir.exists():
            error_msg = f"Alembic versions directory not found: {alembic_versions_dir}"
            logger.error(error_msg)
            result.add_error(error_msg)
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
                result.add_error(error_msg)
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
            result.extend_installed("migrations", installed_files)
            logger.info(f"Installed {len(installed_files)} migration files for {capability_code}")

    def execute_migrations(
        self,
        capability_code: str,
        result: InstallResult
    ):
        """Execute database migrations using Alembic via MigrationOrchestrator"""
        alembic_config = self.local_core_root / "backend" / "alembic.postgres.ini"
        if not alembic_config.exists():
            logger.warning(f"Alembic config not found: {alembic_config}, skipping migration execution")
            result.add_warning("Migrations installed but not executed (alembic config not found)")
            return

        try:
            logger.info(f"Executing database migrations for {capability_code}...")

            # Use MigrationOrchestrator which handles alembic execution properly
            from app.services.migrations.orchestrator import MigrationOrchestrator

            capabilities_root = self.local_core_root / "backend" / "app" / "capabilities"
            alembic_configs = {
                "postgres": alembic_config
            }

            orchestrator = MigrationOrchestrator(capabilities_root, alembic_configs)

            # Execute migrations for postgres (use apply method)
            migration_result = orchestrator.apply("postgres", dry_run=False)

            success = migration_result.get("status") in ["success", "up_to_date"]

            if success:
                logger.info(f"Successfully executed migrations for {capability_code}")
                if result.migration_status is None:
                    result.migration_status = {}
                result.migration_status[capability_code] = "applied"
            else:
                error_msg = f"Migration execution failed via MigrationOrchestrator: {migration_result.get('error', 'Unknown error')}"
                logger.error(error_msg)
                result.add_warning(error_msg)
                if result.migration_status is None:
                    result.migration_status = {}
                result.migration_status[capability_code] = "failed"
        except Exception as e:
            error_msg = f"Migration execution error: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result.add_warning(error_msg)
            if result.migration_status is None:
                result.migration_status = {}
            result.migration_status[capability_code] = "error"

    def _detect_cloud_environment(self) -> bool:
        """
        Detect if running in Cloud environment.

        Returns:
            True if Cloud environment detected, False otherwise
        """
        # Method 1: Check environment variable (highest priority)
        if os.getenv("MINDSCAPE_ENV") == "cloud":
            return True
        if os.getenv("MINDSCAPE_ENV") == "local-core":
            return False

        # Method 2: Check if local_core_root has backend/ directory (Local-Core marker)
        # This works in both local and Docker environments
        local_core_backend = self.local_core_root / "backend"
        if local_core_backend.exists() and local_core_backend.is_dir():
            # We have backend/ directory, so we're in Local-Core
            return False

        # Method 3: Check if local_core_root points to Local-Core directory by path name
        local_core_path_str = str(self.local_core_root)
        if "mindscape-ai-local-core" in local_core_path_str:
            return False

        # Method 4: Check if local_core_root points to Cloud directory by path name
        if "mindscape-ai-cloud" in local_core_path_str:
            return True

        # Method 5: Fallback - check for Cloud marker (mindscape-ai-cloud directory)
        # Only if we can't determine from local_core_root path
        cloud_marker = self.local_core_root.parent / "mindscape-ai-cloud"
        if cloud_marker.exists() and cloud_marker.is_dir():
            # Double-check: if we have backend/, we're in Local-Core
            if local_core_backend.exists() and local_core_backend.is_dir():
                return False
            return True

        return False

    def _get_cloud_web_console_path(self) -> Optional[Path]:
        """
        Get Cloud web-console path.

        Returns:
            Path to Cloud web-console, or None if not found
        """
        if self._cloud_web_console_path is not None:
            return self._cloud_web_console_path

        # Method 1: Check environment variable
        cloud_path = os.getenv("CLOUD_WEB_CONSOLE_PATH")
        if cloud_path:
            path = Path(cloud_path)
            if path.exists():
                self._cloud_web_console_path = path
                return path

        # Method 2: Infer from local_core_root (assume same parent level)
        cloud_root = self.local_core_root.parent / "mindscape-ai-cloud"
        web_console_path = cloud_root / "web-console"
        if web_console_path.exists():
            self._cloud_web_console_path = web_console_path
            return web_console_path

        return None

    def install_ui_components(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        result: InstallResult
    ):
        """
        Install UI components from capability pack to frontend.
        Supports both Local-Core and Cloud environments.
        Unified path: app/capabilities/{capability_code}/components/

        Args:
            cap_dir: Extracted capability directory (from .mindpack)
            capability_code: Capability code
            manifest: Parsed manifest dict
            result: InstallResult to update
        """
        # Detect environment and get frontend directory
        is_cloud = self._detect_cloud_environment()

        # Determine frontend directory with fallback logic
        frontend_dir = None
        if is_cloud:
            # Cloud environment: use Cloud web-console path
            cloud_web_console = self._get_cloud_web_console_path()
            if cloud_web_console is None:
                logger.warning(
                    f"Cloud environment detected but web-console path not found. "
                    f"Falling back to Local-Core path. Set CLOUD_WEB_CONSOLE_PATH env var if needed."
                )
                frontend_dir = self.local_core_root / "web-console" / "src" / "app" / "capabilities"
            else:
                frontend_dir = cloud_web_console / "src" / "app" / "capabilities"
        else:
            # Local-Core environment: use local_core_root
            frontend_dir = self.local_core_root / "web-console" / "src" / "app" / "capabilities"

        # Unified target directory: app/capabilities/{capability_code}/components/
        target_cap_dir = frontend_dir / capability_code / "components"

        # Try to create directory, with fallback to Local-Core if Cloud path fails
        try:
            target_cap_dir.mkdir(parents=True, exist_ok=True)
        except (PermissionError, OSError) as e:
            # If Cloud path fails, fallback to Local-Core path
            if is_cloud:
                logger.warning(
                    f"Failed to write to Cloud path {target_cap_dir}: {e}. "
                    f"Falling back to Local-Core path."
                )
                frontend_dir = self.local_core_root / "web-console" / "src" / "app" / "capabilities"
                target_cap_dir = frontend_dir / capability_code / "components"
                target_cap_dir.mkdir(parents=True, exist_ok=True)
            else:
                # Re-raise if we're already in Local-Core
                raise

        installed_components = []

        # Install entire ui/ directory if it exists (to include all dependencies)
        # This should run even if manifest doesn't define ui_components
        source_ui_dir = cap_dir / "ui"
        if source_ui_dir.exists() and source_ui_dir.is_dir():
            # Copy all files from ui/ directory, preserving subdirectory structure
            for file_path in source_ui_dir.rglob("*"):
                if file_path.is_file():
                    relative_path = file_path.relative_to(source_ui_dir)
                    # Fix: If ui/ has a components/ subdirectory, remove the components/ prefix
                    # to avoid components/components/ duplication
                    # ui/components/X -> components/X (not components/components/X)
                    relative_path_str = str(relative_path)
                    if relative_path_str.startswith("components/"):
                        relative_path = Path(relative_path_str[len("components/"):])
                    # Preserve directory structure: ui/components/X -> components/X, ui/utils/Y -> utils/Y
                    # Unified path: app/capabilities/{code}/components/
                    target_path = frontend_dir / capability_code / "components" / relative_path
                    # Create subdirectories if needed
                    try:
                        target_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(file_path, target_path)
                        logger.debug(f"Installed UI file: {relative_path}")
                        result.add_installed("ui_components", str(relative_path))
                    except (PermissionError, OSError) as e:
                        # If Cloud path fails, fallback to Local-Core path
                        if is_cloud:
                            logger.warning(
                                f"Failed to write to Cloud path {target_path}: {e}. "
                                f"Falling back to Local-Core path."
                            )
                            frontend_dir = self.local_core_root / "web-console" / "src" / "app" / "capabilities"
                            # Use the same corrected relative_path (already fixed above)
                            target_path = frontend_dir / capability_code / "components" / relative_path
                            target_path.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(file_path, target_path)
                            logger.debug(f"Installed UI file (fallback): {relative_path}")
                            result.add_installed("ui_components", str(relative_path))
                        else:
                            # Re-raise if we're already in Local-Core
                            logger.error(f"Failed to install UI file {relative_path}: {e}")
                            result.add_warning(f"Failed to install UI file {relative_path}: {e}")
                            raise

        # Also install individual components specified in manifest
        ui_components = manifest.get("ui_components", [])
        for component_def in ui_components:
            component_code = component_def.get("code")
            component_path = component_def.get("path")

            if not component_path:
                result.add_warning(f"Component {component_code} missing path")
                continue

            # Source: extracted capability pack directory
            source_path = cap_dir / component_path
            if not source_path.exists():
                result.add_warning(f"Component file not found: {component_path}")
                continue

            # Target: Unified path app/capabilities/{code}/components/
            target_path = target_cap_dir / source_path.name

            # Copy component file (always overwrite to ensure latest version)
            try:
                shutil.copy2(source_path, target_path)
            except (PermissionError, OSError) as e:
                # If Cloud path fails, fallback to Local-Core path
                if is_cloud:
                    logger.warning(
                        f"Failed to write to Cloud path {target_path}: {e}. "
                        f"Falling back to Local-Core path."
                    )
                    frontend_dir = self.local_core_root / "web-console" / "src" / "app" / "capabilities"
                    target_cap_dir = frontend_dir / capability_code / "components"
                    target_path = target_cap_dir / source_path.name
                    target_cap_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source_path, target_path)
                    logger.debug(f"Installed UI component (fallback): {component_code}")
                else:
                    # Re-raise if we're already in Local-Core
                    logger.error(f"Failed to install UI component {component_code}: {e}")
                    result.add_warning(f"Failed to install UI component {component_code}: {e}")
                    continue

            installed_components.append(component_code)
            logger.debug(f"Installed UI component: {component_code}")

        if installed_components:
            result.extend_installed("ui_components", installed_components)

    def install_manifest(
        self,
        cap_dir: Path,
        capability_code: str,
        manifest: Dict,
        temp_dir: Optional[Path] = None
    ):
        """
        Install capability manifest

        ⚠️ Hard contract: Manifest must be in both locations
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
            logger.warning(f"manifest.yaml not found in expected locations for {capability_code}")
            return

        target_manifest = target_cap_dir / "manifest.yaml"
        shutil.copy2(manifest_path, target_manifest)
        logger.debug(f"Installed manifest: {capability_code}/manifest.yaml")

    def install_root_files(
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult
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
                result.add_installed("root_files", py_file.name)

