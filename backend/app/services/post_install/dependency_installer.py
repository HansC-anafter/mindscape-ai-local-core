"""
Dependency Installer

负责安装 Python 和 UI 依赖
"""

import json
import logging
import subprocess
import sys
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)


class DependencyInstaller:
    """处理依赖安装（Python 和 UI）"""

    def __init__(self, local_core_root: Path):
        """
        初始化依赖安装器

        Args:
            local_core_root: Local-core 项目根目录
        """
        self.local_core_root = local_core_root

    def install_python_dependencies(
        self,
        cap_dir: Path,
        capability_code: str,
        result
    ):
        """
        安装 Python 依赖（从 requirements.txt）

        Args:
            cap_dir: 能力包目录
            capability_code: 能力代码
            result: InstallResult 对象
        """
        requirements_file = cap_dir / "requirements.txt"
        if not requirements_file.exists():
            logger.debug(f"No requirements.txt found for {capability_code}")
            return

        try:
            logger.info(f"Installing Python dependencies from {requirements_file} for {capability_code}...")

            # Read requirements.txt to log what will be installed
            with open(requirements_file, 'r', encoding='utf-8') as f:
                requirements = f.read().strip()
                if requirements:
                    logger.debug(f"Requirements content:\n{requirements}")

            # Install using pip
            process = subprocess.run(
                [
                    sys.executable, "-m", "pip", "install",
                    "-r", str(requirements_file),
                    "--quiet",  # Reduce output noise
                    "--no-warn-script-location"  # Suppress script location warnings
                ],
                cwd=str(self.local_core_root),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                check=False
            )

            if process.returncode == 0:
                logger.info(f"Successfully installed Python dependencies for {capability_code}")
                result.bootstrap.append("python_dependencies_installed")

                # Log installed packages (from stdout)
                if process.stdout:
                    installed_packages = [line for line in process.stdout.split('\n')
                                       if 'Successfully installed' in line or 'Requirement already satisfied' in line]
                    if installed_packages:
                        logger.debug(f"Installation summary: {installed_packages[:5]}")  # Log first 5
            else:
                error_msg = process.stderr or process.stdout or "Unknown error"
                logger.warning(f"Failed to install Python dependencies for {capability_code}: {error_msg[:500]}")
                result.add_warning(
                    f"Python dependencies installation failed: {error_msg[:200]}"
                )

        except subprocess.TimeoutExpired:
            logger.warning(f"Python dependencies installation timed out for {capability_code}")
            result.add_warning("Python dependencies installation timed out")
        except Exception as e:
            logger.warning(f"Failed to install Python dependencies for {capability_code}: {e}")
            result.add_warning(f"Python dependencies installation error: {str(e)[:200]}")

    def install_ui_dependencies(
        self,
        capability_code: str,
        manifest: Dict,
        result
    ):
        """
        安装 UI 依赖（从 manifest.yaml ui_dependencies 字段）

        Args:
            capability_code: 能力代码
            manifest: 解析后的 manifest 字典
            result: InstallResult 对象
        """
        ui_dependencies = manifest.get('ui_dependencies', {})
        if not ui_dependencies:
            logger.info(f"No UI dependencies declared for {capability_code}")
            return

        logger.info(f"Found UI dependencies for {capability_code}: {ui_dependencies}")

        # Find web-console directory
        web_console_dir = self._find_web_console_dir()
        if not web_console_dir:
            logger.warning("web-console directory not found, skipping UI dependencies installation")
            result.add_warning("web-console directory not found, UI dependencies not installed")
            return

        package_json_path = web_console_dir / "package.json"
        if not package_json_path.exists():
            logger.warning(f"package.json not found at {package_json_path}, skipping UI dependencies installation")
            result.add_warning("package.json not found, UI dependencies not installed")
            return

        # Get required and optional UI dependencies
        required_deps = ui_dependencies.get('required', [])
        optional_deps = ui_dependencies.get('optional', [])

        if not required_deps and not optional_deps:
            logger.debug(f"No UI dependencies to install for {capability_code}")
            return

        # Combine all dependencies
        all_deps = required_deps + optional_deps

        try:
            logger.info(f"Installing UI dependencies for {capability_code}: {all_deps}")

            # Read current package.json to check if dependencies already exist
            with open(package_json_path, 'r', encoding='utf-8') as f:
                package_data = json.load(f)

            dependencies = package_data.get('dependencies', {})
            dev_dependencies = package_data.get('devDependencies', {})

            # Parse dependency strings and check what needs to be installed
            deps_to_install = []
            deps_already_installed = []

            for dep_spec in all_deps:
                if isinstance(dep_spec, str):
                    # Parse "package@version" or just "package"
                    if '@' in dep_spec:
                        dep_name, dep_version = dep_spec.rsplit('@', 1)
                    else:
                        dep_name = dep_spec
                        dep_version = "latest"

                    # Check if already installed
                    if dep_name in dependencies or dep_name in dev_dependencies:
                        existing_version = dependencies.get(dep_name) or dev_dependencies.get(dep_name)
                        deps_already_installed.append(f"{dep_name}@{existing_version}")
                        logger.debug(f"UI dependency {dep_name} already installed: {existing_version}")
                    else:
                        deps_to_install.append(dep_spec)
                elif isinstance(dep_spec, dict):
                    # Support dict format: {name: "package", version: "^1.0.0"}
                    dep_name = dep_spec.get('name', '')
                    dep_version = dep_spec.get('version', 'latest')
                    if not dep_name:
                        continue

                    if dep_name in dependencies or dep_name in dev_dependencies:
                        existing_version = dependencies.get(dep_name) or dev_dependencies.get(dep_name)
                        deps_already_installed.append(f"{dep_name}@{existing_version}")
                        logger.debug(f"UI dependency {dep_name} already installed: {existing_version}")
                    else:
                        deps_to_install.append(f"{dep_name}@{dep_version}" if dep_version != "latest" else dep_name)

            if not deps_to_install:
                logger.info(f"All UI dependencies for {capability_code} are already installed")
                result.bootstrap.append("ui_dependencies_already_installed")
                return

            # Install using npm
            logger.info(f"Installing {len(deps_to_install)} UI dependencies: {deps_to_install}")

            # Build npm install command
            npm_cmd = ["npm", "install", "--save"] + deps_to_install

            process = subprocess.run(
                npm_cmd,
                cwd=str(web_console_dir),
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                check=False
            )

            if process.returncode == 0:
                logger.info(f"Successfully installed UI dependencies for {capability_code}")
                result.bootstrap.append("ui_dependencies_installed")
                result.bootstrap.append(f"ui_dependencies: {', '.join(deps_to_install)}")

                # Log installed packages
                if process.stdout:
                    installed_lines = [line for line in process.stdout.split('\n')
                                     if 'added' in line.lower() or 'installed' in line.lower()]
                    if installed_lines:
                        logger.debug(f"Installation summary: {installed_lines[:5]}")
            else:
                error_msg = process.stderr or process.stdout or "Unknown error"
                logger.warning(f"Failed to install UI dependencies for {capability_code}: {error_msg[:500]}")
                result.add_warning(
                    f"UI dependencies installation failed: {error_msg[:200]}"
                )
                # For optional dependencies, don't fail the installation
                if required_deps:
                    # Only fail if required dependencies failed
                    failed_required = [d for d in deps_to_install if any(rd in d for rd in required_deps)]
                    if failed_required:
                        result.add_warning(
                            f"Required UI dependencies failed to install: {', '.join(failed_required)}"
                        )

        except subprocess.TimeoutExpired:
            logger.warning(f"UI dependencies installation timed out for {capability_code}")
            result.add_warning("UI dependencies installation timed out")
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse package.json: {e}")
            result.add_warning(f"Failed to parse package.json: {str(e)[:200]}")
        except Exception as e:
            logger.warning(f"Failed to install UI dependencies for {capability_code}: {e}")
            result.add_warning(f"UI dependencies installation error: {str(e)[:200]}")

    def _find_web_console_dir(self) -> Path:
        """
        查找 web-console 目录

        Returns:
            web-console 目录路径，如果未找到则返回 None
        """
        possible_paths = [
            self.local_core_root / "web-console",  # Standard location
            self.local_core_root.parent / "web-console",  # If local_core_root is backend/
            Path("/app/web-console"),  # Docker container path
        ]

        logger.info(f"Looking for web-console directory. local_core_root: {self.local_core_root}")
        logger.info(f"Trying paths: {[str(p) for p in possible_paths]}")

        for path in possible_paths:
            logger.debug(f"Checking path: {path}, exists: {path.exists()}")
            if path.exists() and (path / "package.json").exists():
                logger.info(f"Found web-console at: {path}")
                return path

        logger.warning(f"web-console directory not found, tried: {[str(p) for p in possible_paths]}")
        return None

