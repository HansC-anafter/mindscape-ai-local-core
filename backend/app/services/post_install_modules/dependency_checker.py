"""
Dependency Checker

Checks if dependencies are available (Python modules, environment variables, system tools).
"""

import importlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Tuple

logger = logging.getLogger(__name__)


class DependencyChecker:
    """Checks dependency availability"""

    def __init__(
        self,
        local_core_root: Path | None = None,
        capabilities_dir: Path | None = None,
    ):
        self.local_core_root = Path(local_core_root) if local_core_root else None
        self.capabilities_dir = Path(capabilities_dir) if capabilities_dir else None

    def check_dependencies(
        self,
        manifest: Dict,
        result
    ) -> Tuple[List[str], List[str], List[str], List[str], Dict[str, List[str]]]:
        """
        Check all dependencies

        Args:
            manifest: Parsed manifest dictionary
            result: InstallResult object

        Returns:
            Tuple of (missing_required, missing_optional, missing_external, missing_system_tools, degraded_features_map)
        """
        dependencies = manifest.get('dependencies', {})
        if not dependencies:
            # Legacy format or no dependencies declared
            return [], [], [], [], {}

        # Check required Python dependencies
        required_deps = dependencies.get('required', [])
        missing_python_required = []
        for dep in required_deps:
            if not self.is_dependency_available(dep):
                missing_python_required.append(dep)

        # Check optional Python dependencies
        optional_deps = dependencies.get('optional', [])
        missing_python_optional = []
        degraded_features_map = {}
        for opt_dep in optional_deps:
            dep_name = opt_dep if isinstance(opt_dep, str) else opt_dep.get('name', '')
            if not dep_name:
                continue

            if not self.is_dependency_available(dep_name):
                missing_python_optional.append(dep_name)
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

        missing_pack_required, missing_pack_optional = self._check_pack_dependencies(
            manifest.get("pack_dependencies", {})
        )
        missing_contract_imports = self._check_contract_imports(
            manifest.get("contract_imports", [])
        )
        missing_required = [
            *missing_python_required,
            *missing_pack_required,
            *missing_contract_imports,
        ]
        missing_optional = [
            *missing_python_optional,
            *missing_pack_optional,
        ]

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
        if missing_python_required:
            result.missing_dependencies["python_required"] = missing_python_required
        if missing_pack_required:
            result.missing_dependencies["pack_dependencies_required"] = missing_pack_required
        if missing_pack_optional:
            result.missing_dependencies["pack_dependencies_optional"] = missing_pack_optional
        if missing_contract_imports:
            result.missing_dependencies["contract_imports"] = missing_contract_imports

        return missing_required, missing_optional, missing_external, missing_system_tools, degraded_features_map

    def _check_pack_dependencies(self, pack_dependencies: Dict) -> Tuple[List[str], List[str]]:
        if not self.capabilities_dir or not isinstance(pack_dependencies, dict):
            return [], []

        missing_required = [
            dep
            for dep in self._dependency_codes(pack_dependencies.get("required", []))
            if not (self.capabilities_dir / dep).exists()
        ]
        missing_optional = [
            dep
            for dep in self._dependency_codes(pack_dependencies.get("optional", []))
            if not (self.capabilities_dir / dep).exists()
        ]
        return missing_required, missing_optional

    def _check_contract_imports(self, contract_imports: List[Dict]) -> List[str]:
        if not self.local_core_root or not isinstance(contract_imports, list):
            return []

        contracts = self._load_contract_registry()
        missing = []
        for contract_import in contract_imports:
            if not isinstance(contract_import, dict):
                continue
            contract_id = str(contract_import.get("contract_id") or "").strip()
            provider_pack = str(contract_import.get("provider_pack") or "").strip()
            version_range = str(contract_import.get("version_range") or "").strip()
            if not contract_id or not provider_pack:
                continue
            if any(
                contract.get("contract_id") == contract_id
                and contract.get("provider_pack") == provider_pack
                for contract in contracts
            ):
                continue
            label = f"{contract_id}@{provider_pack}"
            if version_range:
                label = f"{label} ({version_range})"
            missing.append(label)
        return missing

    def _load_contract_registry(self) -> List[Dict]:
        if not self.local_core_root:
            return []
        registry_path = self.local_core_root / "data" / "runtime_contracts" / "registry.json"
        if not registry_path.exists():
            return []
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return []
        contracts = payload.get("contracts", [])
        return contracts if isinstance(contracts, list) else []

    def _dependency_codes(self, dependencies: List) -> List[str]:
        codes = []
        for dep in dependencies or []:
            if isinstance(dep, str):
                codes.append(dep)
            elif isinstance(dep, dict):
                code = dep.get("code") or dep.get("name")
                if code:
                    codes.append(str(code))
        return codes

    def is_dependency_available(self, dep_name: str) -> bool:
        """
        Check if Python module dependency is available

        Args:
            dep_name: Dependency name (e.g., 'contracts.execution_context', 'core_llm')

        Returns:
            True if available
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
        """Check if environment variable is set"""
        return bool(os.getenv(env_var))

    def is_system_tool_available(self, tool_name: str) -> bool:
        """
        Check if system tool is available in PATH

        Args:
            tool_name: System tool name (e.g., 'ffprobe', 'ffmpeg')

        Returns:
            True if available
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
