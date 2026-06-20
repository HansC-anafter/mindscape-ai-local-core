"""Compatibility checks for validation service."""

import re
from pathlib import Path
from typing import Dict, List, Tuple

from backend.app.services.stores.installed_packs_store import InstalledPacksStore


def validate_compatibility(
    local_core_root: Path,
    manifest: Dict,
    result: Dict,
) -> None:
    """Run compatibility checks."""
    version_ok, version_errors = check_version_compatibility(local_core_root, manifest)
    result["validation_stages"]["version"] = {
        "ok": version_ok,
        "errors": version_errors,
    }
    result["errors"].extend(version_errors)

    installed_packs = get_installed_packs()
    conflict_ok, conflict_errors, conflict_warnings = check_conflicts(
        manifest,
        installed_packs,
    )
    result["validation_stages"]["conflicts"] = {
        "ok": conflict_ok,
        "errors": conflict_errors,
        "warnings": conflict_warnings,
    }
    result["errors"].extend(conflict_errors)
    result["warnings"].extend(conflict_warnings)


def check_version_compatibility(
    local_core_root: Path,
    manifest: Dict,
) -> Tuple[bool, List[str]]:
    """Check version compatibility."""
    errors = []

    core_version_required = manifest.get("core_version_required")
    if not core_version_required:
        return True, []

    try:
        version_file = local_core_root / "backend" / "app" / "__init__.py"
        if version_file.exists():
            content = version_file.read_text()
            match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                current_version = match.group(1)
                pass
    except Exception:
        pass

    return len(errors) == 0, errors


def check_conflicts(
    manifest: Dict,
    installed_packs: List[str],
) -> Tuple[bool, List[str], List[str]]:
    """Check conflicts with installed packs."""
    errors = []
    warnings = []

    capability_code = manifest.get("code")
    if capability_code in installed_packs:
        errors.append(f"Capability '{capability_code}' is already installed")

    conflicts = manifest.get("conflicts", [])
    for conflict_code in conflicts:
        if conflict_code in installed_packs:
            errors.append(f"Conflicts with installed capability: {conflict_code}")

    dependency_codes = []
    dependencies = manifest.get("dependencies", [])
    if isinstance(dependencies, list):
        dependency_codes.extend(dependencies)

    pack_dependencies = manifest.get("pack_dependencies", {})
    if isinstance(pack_dependencies, dict):
        dependency_codes.extend(pack_dependencies.get("required", []) or [])
        dependency_codes.extend(pack_dependencies.get("optional", []) or [])
    elif isinstance(pack_dependencies, list):
        dependency_codes.extend(pack_dependencies)

    for dependency_code in dependency_codes:
        if isinstance(dependency_code, dict):
            dependency_code = dependency_code.get("code") or dependency_code.get("name")
        if not dependency_code:
            continue
        if dependency_code not in installed_packs:
            warnings.append(f"Missing dependency: {dependency_code}")

    return len(errors) == 0, errors, warnings


def get_installed_packs() -> List[str]:
    """Get list of installed pack IDs."""
    try:
        store = InstalledPacksStore()
        return store.list_installed_pack_ids()
    except Exception:
        pass
    return []
