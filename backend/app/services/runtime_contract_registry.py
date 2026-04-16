"""Install-time runtime contract registry and legacy alias generation."""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List

from .runtime_contract_paths import resolve_runtime_contracts_root

logger = logging.getLogger(__name__)

_NAMESPACE_INIT = '''"""Runtime-generated namespace package for compatibility aliases."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
'''


@dataclass
class RuntimeContractSyncResult:
    """Outcome from syncing runtime contract exports for a single pack."""

    changed: bool
    requires_restart: bool
    registry_path: Path
    alias_modules: List[str]


class RuntimeContractRegistry:
    """Persist exported pack contracts and generate legacy alias modules."""

    def __init__(self, local_core_root: Path):
        self.local_core_root = Path(local_core_root)
        self.runtime_contracts_root = resolve_runtime_contracts_root(local_core_root)
        self.registry_path = self.runtime_contracts_root / "registry.json"

    def sync_pack_contracts(
        self,
        capability_code: str,
        manifest: Dict[str, Any],
    ) -> RuntimeContractSyncResult:
        """Rewrite the registry and alias tree for one installed pack."""
        previous_registry = self._load_registry()
        exports = self._normalize_contract_exports(capability_code, manifest)
        next_registry = {
            "version": 1,
            "contracts": [
                entry
                for entry in previous_registry.get("contracts", [])
                if entry.get("provider_pack") != capability_code
            ]
            + exports,
        }
        next_registry["contracts"] = sorted(
            next_registry["contracts"],
            key=lambda entry: (
                entry.get("provider_pack", ""),
                entry.get("contract_id", ""),
                entry.get("module", ""),
            ),
        )

        changed = previous_registry != next_registry
        self.runtime_contracts_root.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(
            json.dumps(next_registry, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        alias_modules = self._rewrite_alias_modules(next_registry)
        return RuntimeContractSyncResult(
            changed=changed,
            requires_restart=changed,
            registry_path=self.registry_path,
            alias_modules=alias_modules,
        )

    def _load_registry(self) -> Dict[str, Any]:
        if not self.registry_path.exists():
            return {"version": 1, "contracts": []}
        try:
            return json.loads(self.registry_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(
                "Failed to parse runtime contract registry %s: %s; rebuilding",
                self.registry_path,
                exc,
            )
            return {"version": 1, "contracts": []}

    def _normalize_contract_exports(
        self,
        capability_code: str,
        manifest: Dict[str, Any],
    ) -> List[Dict[str, Any]]:
        exports = manifest.get("contract_exports", []) or []
        normalized: List[Dict[str, Any]] = []
        for index, export in enumerate(exports):
            if not isinstance(export, dict):
                logger.warning(
                    "[%s] Ignoring malformed contract export at index %s: %r",
                    capability_code,
                    index,
                    export,
                )
                continue
            contract_id = str(export.get("contract_id", "")).strip()
            module = str(export.get("module", "")).strip()
            version = str(export.get("version", "")).strip()
            if not contract_id or not module or not version:
                logger.warning(
                    "[%s] Ignoring incomplete contract export %r",
                    capability_code,
                    export,
                )
                continue
            legacy_aliases = [
                str(alias).strip()
                for alias in export.get("legacy_aliases", []) or []
                if str(alias).strip()
            ]
            normalized.append(
                {
                    "provider_pack": capability_code,
                    "contract_id": contract_id,
                    "module": module,
                    "version": version,
                    "legacy_aliases": legacy_aliases,
                }
            )
        return normalized

    def _rewrite_alias_modules(self, registry: Dict[str, Any]) -> List[str]:
        alias_modules: List[str] = []
        for child in (
            self.runtime_contracts_root.iterdir()
            if self.runtime_contracts_root.exists()
            else []
        ):
            if child.name == "registry.json":
                continue
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()

        for contract in registry.get("contracts", []):
            canonical_module = contract.get("module", "")
            for alias in contract.get("legacy_aliases", []) or []:
                if not alias:
                    continue
                alias_modules.append(alias)
                self._write_alias_module(alias, canonical_module)
        return sorted(alias_modules)

    def _write_alias_module(self, alias: str, canonical_module: str) -> None:
        alias_parts = alias.split(".")
        if len(alias_parts) < 2:
            logger.warning("Skipping unsupported legacy alias %s", alias)
            return

        package_parts = alias_parts[:-1]
        module_name = alias_parts[-1]

        current_dir = self.runtime_contracts_root
        for package_part in package_parts:
            current_dir = current_dir / package_part
            current_dir.mkdir(parents=True, exist_ok=True)
            init_path = current_dir / "__init__.py"
            init_path.write_text(_NAMESPACE_INIT, encoding="utf-8")

        module_path = current_dir / f"{module_name}.py"
        module_path.write_text(
            self._render_alias_module(alias, canonical_module),
            encoding="utf-8",
        )

    @staticmethod
    def _render_alias_module(alias: str, canonical_module: str) -> str:
        return (
            f'"""Runtime-generated compatibility alias for `{alias}`."""\n\n'
            f"from {canonical_module} import *  # noqa: F401,F403\n"
        )
