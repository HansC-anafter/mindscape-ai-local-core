"""
Dependency Checker

检查依赖是否可用（Python模块、环境变量、系统工具）
"""

import importlib
import logging
import os
import subprocess
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class DependencyChecker:
    """检查依赖可用性"""

    def check_dependencies(
        self,
        manifest: Dict,
        result
    ) -> Tuple[List[str], List[str], List[str], List[str], Dict[str, List[str]]]:
        """
        检查所有依赖

        Args:
            manifest: 解析后的 manifest 字典
            result: InstallResult 对象

        Returns:
            (missing_required, missing_optional, missing_external, missing_system_tools, degraded_features_map)
        """
        dependencies = manifest.get('dependencies', {})
        if not dependencies:
            # Legacy format or no dependencies declared
            return [], [], [], [], {}

        # Check required dependencies
        required_deps = dependencies.get('required', [])
        missing_required = []
        for dep in required_deps:
            if not self.is_dependency_available(dep):
                missing_required.append(dep)

        # Check optional dependencies
        optional_deps = dependencies.get('optional', [])
        missing_optional = []
        degraded_features_map = {}
        for opt_dep in optional_deps:
            dep_name = opt_dep if isinstance(opt_dep, str) else opt_dep.get('name', '')
            if not dep_name:
                continue

            if not self.is_dependency_available(dep_name):
                missing_optional.append(dep_name)
                # Build degraded features map
                if isinstance(opt_dep, dict):
                    degraded_features = opt_dep.get('degraded_features', [])
                    if degraded_features:
                        degraded_features_map[dep_name] = degraded_features

        # Check external services
        external_services = dependencies.get('external_services', [])
        missing_external = []
        for ext_svc in external_services:
            svc_name = ext_svc if isinstance(ext_svc, str) else ext_svc.get('name', '')
            if not svc_name:
                continue

            env_var = ext_svc.get('env_var') if isinstance(ext_svc, dict) else None
            if env_var and not self.is_env_var_set(env_var):
                missing_external.append(svc_name)
                # Add to degraded features map
                if isinstance(ext_svc, dict):
                    degraded_features = ext_svc.get('degraded_features', [])
                    if degraded_features:
                        degraded_features_map[svc_name] = degraded_features

        # Check system tools
        system_tools = dependencies.get('system_tools', [])
        missing_system_tools = []
        for tool_config in system_tools:
            tool_name = tool_config if isinstance(tool_config, str) else tool_config.get('name', '')
            if not tool_name:
                continue

            if not self.is_system_tool_available(tool_name):
                missing_system_tools.append(tool_name)
                # Add to degraded features map
                if isinstance(tool_config, dict):
                    degraded_features = tool_config.get('degraded_features', [])
                    install_hint = tool_config.get('install_hint', '')
                    if degraded_features:
                        degraded_features_map[tool_name] = degraded_features
                    # Add install hint to result warnings
                    if install_hint:
                        result.add_warning(
                            f"System tool '{tool_name}' not found. {install_hint}"
                        )
                    else:
                        result.add_warning(
                            f"System tool '{tool_name}' not found. "
                            f"Some features may be degraded. "
                            f"Install with: apt-get install {tool_name} (Linux) or brew install {tool_name} (macOS)"
                        )

        # Add to result for reporting
        if missing_required:
            if not result.missing_dependencies:
                result.missing_dependencies = {}
            result.missing_dependencies["required"] = missing_required
        if missing_optional:
            if not result.missing_dependencies:
                result.missing_dependencies = {}
            result.missing_dependencies["optional"] = missing_optional
        if missing_external:
            if not result.missing_dependencies:
                result.missing_dependencies = {}
            result.missing_dependencies["external_services"] = missing_external
        if missing_system_tools:
            if not result.missing_dependencies:
                result.missing_dependencies = {}
            result.missing_dependencies["system_tools"] = missing_system_tools

        return missing_required, missing_optional, missing_external, missing_system_tools, degraded_features_map

    def is_dependency_available(self, dep_name: str) -> bool:
        """
        检查 Python 模块依赖是否可用

        Args:
            dep_name: 依赖名称（如 'contracts.execution_context', 'core_llm'）

        Returns:
            True 如果可用
        """
        try:
            # Try to import the dependency
            importlib.import_module(dep_name)
            return True
        except (ImportError, ModuleNotFoundError, ValueError):
            # Check if it's a fallback shim
            if dep_name == 'contracts.execution_context':
                try:
                    importlib.import_module('mindscape.shims.execution_context')
                    return True  # Fallback available
                except (ImportError, ModuleNotFoundError):
                    pass
            return False

    def is_env_var_set(self, env_var: str) -> bool:
        """检查环境变量是否已设置"""
        return bool(os.getenv(env_var))

    def is_system_tool_available(self, tool_name: str) -> bool:
        """
        检查系统工具是否在 PATH 中可用

        Args:
            tool_name: 系统工具名称（如 'ffprobe', 'ffmpeg'）

        Returns:
            True 如果可用
        """
        try:
            # Use 'which' command to check if tool exists in PATH
            result = subprocess.run(
                ['which', tool_name],
                capture_output=True,
                text=True,
                timeout=2
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            # 'which' command not available or timed out, try alternative method
            try:
                # Try to run the tool with --version or --help
                result = subprocess.run(
                    [tool_name, '--version'],
                    capture_output=True,
                    text=True,
                    timeout=2
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False

