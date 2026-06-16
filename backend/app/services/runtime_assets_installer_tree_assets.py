import logging
import shutil
from pathlib import Path

from .install_result import InstallResult
from .runtime_assets_installer_support import (
    RUNTIME_NAMESPACE_DIRS,
    SCRIPT_DIR_EXCLUDES,
    SCRIPT_FILE_EXCLUDES,
    SCRIPT_SUFFIX_EXCLUDES,
    _clear_directory_contents,
)

logger = logging.getLogger("app.services.runtime_assets_installer")


class RuntimeAssetsInstallerTreeAssetsMixin:
    def install_workflows(self, cap_dir: Path, capability_code: str, result: InstallResult):
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

    def install_scripts(self, cap_dir: Path, capability_code: str, result: InstallResult):
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
            if tool_file.name.startswith("__") and tool_file.name != "__init__.py":
                continue

            target_tool = target_tools_dir / tool_file.name
            shutil.copy2(tool_file, target_tool)
            tool_name = tool_file.stem
            result.add_installed("tools", tool_name)
            logger.debug(f"Installed tool: {tool_name}")

        for item in tools_dir.iterdir():
            if not item.is_dir():
                continue
            if item.name.startswith("__"):
                continue
            target_subdir = target_tools_dir / item.name
            if target_subdir.exists():
                shutil.rmtree(target_subdir)
            shutil.copytree(item, target_subdir)
            logger.debug(f"Installed tools subdirectory: {item.name}")
            result.add_installed("tools_dirs", item.name)

    def install_services(self, cap_dir: Path, capability_code: str, result: InstallResult):
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

    def install_runtime_namespace_dirs(
        self,
        cap_dir: Path,
        capability_code: str,
        result: InstallResult,
    ):
        """Install pack-local runtime namespace packages."""
        for dirname in sorted(RUNTIME_NAMESPACE_DIRS):
            source_dir = cap_dir / dirname
            if not source_dir.exists():
                continue
            if not source_dir.is_dir():
                result.add_warning(
                    f"Skipping non-directory runtime namespace asset: {dirname}"
                )
                continue

            target_dir = self.capabilities_dir / capability_code / dirname
            if target_dir.exists():
                shutil.rmtree(target_dir)
            shutil.copytree(
                source_dir,
                target_dir,
                ignore=shutil.ignore_patterns(
                    "__pycache__",
                    "*.pyc",
                    "*.pyo",
                    ".DS_Store",
                ),
            )
            result.add_installed("runtime_namespace_dirs", dirname)
            logger.debug("Installed runtime namespace directory: %s", dirname)

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
                if not api_file.name.startswith("__"):
                    api_name = api_file.stem
                    result.add_installed("api_endpoints", api_name)
                    logger.debug(f"Installed API endpoint: {api_name}")
                else:
                    logger.debug(f"Installed API file: {api_file.name}")

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

        for schema_file in schema_dir.glob("*.py"):
            target_schema = target_schema_dir / schema_file.name
            shutil.copy2(schema_file, target_schema)
            schema_name = schema_file.stem
            if not schema_name.startswith("__"):
                result.add_installed("schema_modules", schema_name)
            logger.debug(f"Installed schema module: {schema_file.name}")

        for item in schema_dir.iterdir():
            if item.is_dir() and not item.name.startswith("__"):
                target_subdir = target_schema_dir / item.name
                if target_subdir.exists():
                    shutil.rmtree(target_subdir)
                shutil.copytree(item, target_subdir)
                logger.debug(f"Installed schema subdirectory: {item.name}")
                result.add_installed("schema_data_dirs", item.name)
