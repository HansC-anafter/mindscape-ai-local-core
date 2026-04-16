"""
Dependency Checker

Checks Python dependencies, installed pack dependencies, contract imports,
environment variables, and system tools during post-install validation.
"""

from __future__ import annotations

import importlib
import json
import logging
import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from packaging.version import InvalidVersion, Version

from app.services.runtime_contract_paths import resolve_runtime_contracts_root

logger = logging.getLogger(__name__)


class DependencyChecker:
    """Checks dependency availability across Python, pack, and contract lanes."""

    def __init__(
        self,
        local_core_root: Optional[Path] = None,
        capabilities_dir: Optional[Path] = None,
    ):
        self.local_core_root = Path(local_core_root) if local_core_root else None
        self.capabilities_dir = Path(capabilities_dir) if capabilities_dir else None

    def check_dependencies(
        self,
        manifest: Dict,
        result,
    ) -> Tuple[List[str], List[str], List[str], List[str], Dict[str, List[str]]]:
        """
        Check all dependencies.

        Returns:
            (missing_required, missing_optional, missing_external, missing_system_tools, degraded_features_map)
        """
        dependencies = manifest.get("dependencies", {})
        known_pack_ids = self._get_known_pack_ids()
        required_pack_deps, optional_pack_deps = self._extract_pack_dependencies(
            manifest,
            known_pack_ids,
        )
        declared_pack_ids = known_pack_ids.union(required_pack_deps).union(
            optional_pack_deps
        )

        python_required = self._extract_required_python_dependencies(
            dependencies,
            declared_pack_ids,
        )
        missing_python_required = [
            dep for dep in python_required if not self.is_dependency_available(dep)
        ]

        optional_python, degraded_features_map = self._extract_optional_python_dependencies(
            dependencies,
            declared_pack_ids,
        )
        self._merge_degraded_features(
            degraded_features_map,
            self._extract_pack_degraded_features(dependencies, declared_pack_ids),
        )
        missing_python_optional = [
            dep_name
            for dep_name in optional_python
            if not self.is_dependency_available(dep_name)
        ]

        installed_pack_ids = self._get_installed_pack_ids()
        missing_required_pack = [
            dep for dep in required_pack_deps if dep not in installed_pack_ids
        ]
        missing_optional_pack = [
            dep for dep in optional_pack_deps if dep not in installed_pack_ids
        ]

        missing_contract_imports = self._resolve_contract_import_issues(
            manifest.get("contract_imports", []) or []
        )

        external_services = (
            dependencies.get("external_services", [])
            if isinstance(dependencies, dict)
            else []
        )
        missing_external = []
        for ext_svc in external_services:
            svc_name = ext_svc if isinstance(ext_svc, str) else ext_svc.get("name", "")
            if not svc_name:
                continue

            env_var = ext_svc.get("env_var") if isinstance(ext_svc, dict) else None
            if env_var and not self.is_env_var_set(env_var):
                missing_external.append(svc_name)
                if isinstance(ext_svc, dict):
                    degraded_features = ext_svc.get("degraded_features", [])
                    if degraded_features:
                        degraded_features_map[svc_name] = degraded_features

        system_tools = (
            dependencies.get("system_tools", [])
            if isinstance(dependencies, dict)
            else []
        )
        missing_system_tools = []
        for tool_config in system_tools:
            tool_name = (
                tool_config if isinstance(tool_config, str) else tool_config.get("name", "")
            )
            if not tool_name:
                continue

            if not self.is_system_tool_available(tool_name):
                missing_system_tools.append(tool_name)
                if isinstance(tool_config, dict):
                    degraded_features = tool_config.get("degraded_features", [])
                    install_hint = tool_config.get("install_hint", "")
                    if degraded_features:
                        degraded_features_map[tool_name] = degraded_features
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

        missing_required = (
            missing_python_required
            + missing_required_pack
            + missing_contract_imports
        )
        missing_optional = missing_python_optional + missing_optional_pack

        if missing_required:
            result.missing_dependencies["required"] = missing_required
        if missing_optional:
            result.missing_dependencies["optional"] = missing_optional
        if missing_external:
            result.missing_dependencies["external_services"] = missing_external
        if missing_system_tools:
            result.missing_dependencies["system_tools"] = missing_system_tools
        if missing_python_required:
            result.missing_dependencies["python_required"] = missing_python_required
        if missing_python_optional:
            result.missing_dependencies["python_optional"] = missing_python_optional
        if missing_required_pack:
            result.missing_dependencies["pack_dependencies_required"] = missing_required_pack
        if missing_optional_pack:
            result.missing_dependencies["pack_dependencies_optional"] = missing_optional_pack
        if missing_contract_imports:
            result.missing_dependencies["contract_imports"] = missing_contract_imports

        return (
            missing_required,
            missing_optional,
            missing_external,
            missing_system_tools,
            degraded_features_map,
        )

    def _extract_required_python_dependencies(
        self,
        dependencies: object,
        known_pack_ids: set[str],
    ) -> List[str]:
        if isinstance(dependencies, list):
            return [
                dep
                for dep in dependencies
                if isinstance(dep, str) and dep not in known_pack_ids
            ]

        if not isinstance(dependencies, dict):
            return []

        python_dependencies: List[str] = []
        for dep in dependencies.get("required", []) or []:
            if not isinstance(dep, str):
                continue
            if dep in known_pack_ids:
                continue
            python_dependencies.append(dep)
        return python_dependencies

    def _extract_optional_python_dependencies(
        self,
        dependencies: object,
        known_pack_ids: set[str],
    ) -> Tuple[List[str], Dict[str, List[str]]]:
        if not isinstance(dependencies, dict):
            return [], {}

        missing_candidates: List[str] = []
        degraded_features_map: Dict[str, List[str]] = {}
        for opt_dep in dependencies.get("optional", []) or []:
            dep_name = ""
            if isinstance(opt_dep, str):
                if opt_dep in known_pack_ids:
                    continue
                dep_name = opt_dep
            elif isinstance(opt_dep, dict):
                name = str(opt_dep.get("name", "")).strip()
                code = str(opt_dep.get("code", "")).strip()
                if name:
                    dep_name = name
                elif code and code not in known_pack_ids:
                    dep_name = code
                if dep_name and dep_name in known_pack_ids:
                    continue
                if dep_name:
                    degraded_features = opt_dep.get("degraded_features", [])
                    if degraded_features:
                        degraded_features_map[dep_name] = degraded_features

            if dep_name:
                missing_candidates.append(dep_name)
        return missing_candidates, degraded_features_map

    def _extract_pack_degraded_features(
        self,
        dependencies: object,
        known_pack_ids: set[str],
    ) -> Dict[str, List[str]]:
        if not isinstance(dependencies, dict):
            return {}

        degraded_features_map: Dict[str, List[str]] = {}
        for opt_dep in dependencies.get("optional", []) or []:
            if not isinstance(opt_dep, dict):
                continue
            code = str(opt_dep.get("code", "")).strip()
            name = str(opt_dep.get("name", "")).strip()
            pack_id = ""
            if code and code in known_pack_ids:
                pack_id = code
            elif name and name in known_pack_ids:
                pack_id = name
            if not pack_id:
                continue
            degraded_features = opt_dep.get("degraded_features", [])
            if degraded_features:
                degraded_features_map[pack_id] = list(degraded_features)
        return degraded_features_map

    def _extract_pack_dependencies(
        self,
        manifest: Dict,
        known_pack_ids: set[str],
    ) -> Tuple[List[str], List[str]]:
        explicit_pack_dependencies = manifest.get("pack_dependencies")
        if isinstance(explicit_pack_dependencies, dict):
            required = [
                dep
                for dep in explicit_pack_dependencies.get("required", []) or []
                if isinstance(dep, str) and dep.strip()
            ]
            optional = [
                dep
                for dep in explicit_pack_dependencies.get("optional", []) or []
                if isinstance(dep, str) and dep.strip()
            ]
            return required, optional

        dependencies = manifest.get("dependencies")
        if isinstance(dependencies, list):
            required = [
                dep for dep in dependencies if isinstance(dep, str) and dep in known_pack_ids
            ]
            return required, []

        if not isinstance(dependencies, dict):
            return [], []

        required = [
            dep
            for dep in dependencies.get("required", []) or []
            if isinstance(dep, str) and dep in known_pack_ids
        ]
        optional: List[str] = []
        for opt_dep in dependencies.get("optional", []) or []:
            if isinstance(opt_dep, str) and opt_dep in known_pack_ids:
                optional.append(opt_dep)
                continue
            if not isinstance(opt_dep, dict):
                continue
            code = str(opt_dep.get("code", "")).strip()
            name = str(opt_dep.get("name", "")).strip()
            if code and not name and code in known_pack_ids:
                optional.append(code)
        return required, optional

    def _merge_degraded_features(
        self,
        target: Dict[str, List[str]],
        source: Dict[str, List[str]],
    ) -> None:
        for dep_name, features in source.items():
            if dep_name not in target:
                target[dep_name] = list(features)
                continue
            merged = list(target[dep_name])
            for feature in features:
                if feature not in merged:
                    merged.append(feature)
            target[dep_name] = merged

    def _get_known_pack_ids(self) -> set[str]:
        known_pack_ids: set[str] = set()
        if self.capabilities_dir and self.capabilities_dir.exists():
            for item in self.capabilities_dir.iterdir():
                if item.is_dir():
                    known_pack_ids.add(item.name)
        return known_pack_ids

    def _get_installed_pack_ids(self) -> set[str]:
        installed_pack_ids = self._get_known_pack_ids()
        if not self.local_core_root:
            return installed_pack_ids
        try:
            from app.services.stores.installed_packs_store import InstalledPacksStore

            installed_pack_ids.update(InstalledPacksStore().list_installed_pack_ids())
        except Exception:
            pass
        return installed_pack_ids

    def _resolve_contract_import_issues(
        self,
        contract_imports: List[Dict],
    ) -> List[str]:
        if not contract_imports:
            return []

        exports = self._load_contract_exports()
        missing: List[str] = []
        for contract_import in contract_imports:
            if not isinstance(contract_import, dict):
                continue
            contract_id = str(contract_import.get("contract_id", "")).strip()
            provider_pack = str(contract_import.get("provider_pack", "")).strip()
            version_range = str(contract_import.get("version_range", "")).strip()
            label = f"{contract_id}@{provider_pack} ({version_range})"
            candidates = [
                export
                for export in exports
                if export.get("contract_id") == contract_id
                and export.get("provider_pack") == provider_pack
            ]
            if not candidates:
                missing.append(label)
                continue
            if not any(
                self._version_range_matches(version_range, export.get("version", ""))
                for export in candidates
            ):
                missing.append(label)
        return missing

    def _load_contract_exports(self) -> List[Dict]:
        if not self.local_core_root:
            return []
        registry_path = resolve_runtime_contracts_root(self.local_core_root) / "registry.json"
        if not registry_path.exists():
            return []
        try:
            payload = json.loads(registry_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to parse runtime contract registry %s: %s", registry_path, exc)
            return []
        contracts = payload.get("contracts", [])
        return [contract for contract in contracts if isinstance(contract, dict)]

    def _version_range_matches(self, version_range: str, exported_version: str) -> bool:
        if not version_range or not exported_version:
            return False
        try:
            exported = Version(exported_version)
        except InvalidVersion:
            return False

        version_range = version_range.strip()
        if version_range.startswith("^"):
            base = version_range[1:].strip()
            try:
                minimum = Version(base)
            except InvalidVersion:
                return False
            return exported.major == minimum.major and exported >= minimum

        if version_range.startswith("=="):
            try:
                return exported == Version(version_range[2:].strip())
            except InvalidVersion:
                return False

        try:
            return exported == Version(version_range)
        except InvalidVersion:
            return False

    def is_dependency_available(self, dep_name: str) -> bool:
        """Check if Python module dependency is available."""
        try:
            importlib.import_module(dep_name)
            return True
        except (ImportError, ModuleNotFoundError, ValueError):
            if dep_name == "contracts.execution_context":
                try:
                    importlib.import_module("mindscape.shims.execution_context")
                    return True
                except (ImportError, ModuleNotFoundError):
                    pass
            return False

    def is_env_var_set(self, env_var: str) -> bool:
        """Check if environment variable is set."""
        return bool(os.getenv(env_var))

    def is_system_tool_available(self, tool_name: str) -> bool:
        """Check if system tool is available in PATH."""
        try:
            result = subprocess.run(
                ["which", tool_name],
                capture_output=True,
                text=True,
                timeout=2,
            )
            return result.returncode == 0
        except (subprocess.TimeoutExpired, FileNotFoundError):
            try:
                result = subprocess.run(
                    [tool_name, "--version"],
                    capture_output=True,
                    text=True,
                    timeout=2,
                )
                return result.returncode == 0
            except (subprocess.TimeoutExpired, FileNotFoundError):
                return False
