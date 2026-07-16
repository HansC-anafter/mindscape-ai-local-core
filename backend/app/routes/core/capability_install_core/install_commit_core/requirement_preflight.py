"""Side-effect-free dependency and bootstrap preflight for atomic installs."""

from __future__ import annotations

import json
from importlib import metadata
from pathlib import Path
from typing import Any, Mapping

from packaging.requirements import InvalidRequirement, Requirement


_READ_ONLY_BOOTSTRAP_TYPES = {"cloud_provider_runtime_init"}


def validate_atomic_install_requirements(
    *,
    local_core_root: Path,
    candidate_dir: Path,
    manifest: Mapping[str, Any],
) -> list[str]:
    """Return exact blockers without installing packages or executing hooks."""

    blockers: list[str] = []
    blockers.extend(_python_requirement_blockers(candidate_dir))
    blockers.extend(_ui_requirement_blockers(local_core_root, manifest))
    for index, bootstrap in enumerate(manifest.get("bootstrap", []) or []):
        if not isinstance(bootstrap, Mapping):
            blockers.append(f"bootstrap_invalid:{index}")
            continue
        bootstrap_type = str(bootstrap.get("type") or "").strip()
        if bootstrap_type not in _READ_ONLY_BOOTSTRAP_TYPES:
            blockers.append(
                f"bootstrap_not_atomic:{index}:{bootstrap_type or 'missing_type'}"
            )
    return blockers


def _python_requirement_blockers(candidate_dir: Path) -> list[str]:
    path = candidate_dir / "requirements.txt"
    if not path.exists():
        return []
    blockers: list[str] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith(("-", "http://", "https://", "git+")):
            blockers.append(f"python_requirement_not_preflightable:{line_number}")
            continue
        try:
            requirement = Requirement(line)
        except InvalidRequirement:
            blockers.append(f"python_requirement_invalid:{line_number}")
            continue
        if requirement.marker and not requirement.marker.evaluate():
            continue
        try:
            installed = metadata.version(requirement.name)
        except metadata.PackageNotFoundError:
            blockers.append(f"python_requirement_missing:{requirement.name}")
            continue
        if requirement.specifier and installed not in requirement.specifier:
            blockers.append(
                f"python_requirement_version_mismatch:{requirement.name}:{installed}"
            )
    return blockers


def _ui_requirement_blockers(
    local_core_root: Path,
    manifest: Mapping[str, Any],
) -> list[str]:
    declaration = manifest.get("ui_dependencies") or {}
    if not isinstance(declaration, Mapping):
        return ["ui_dependencies_invalid"]
    required = declaration.get("required") or []
    if not required:
        return []
    package_json = local_core_root / "web-console" / "package.json"
    if not package_json.exists():
        return ["ui_package_manifest_missing"]
    payload = json.loads(package_json.read_text(encoding="utf-8"))
    installed = {
        **dict(payload.get("dependencies") or {}),
        **dict(payload.get("devDependencies") or {}),
    }
    blockers: list[str] = []
    for item in required:
        if isinstance(item, Mapping):
            name = str(item.get("name") or "").strip()
        else:
            raw = str(item or "").strip()
            if raw.startswith("@"):
                slash = raw.find("/")
                at = raw.find("@", slash + 1)
                name = raw if at < 0 else raw[:at]
            else:
                name = raw.split("@", 1)[0]
        if not name:
            blockers.append("ui_requirement_invalid")
        elif name not in installed:
            blockers.append(f"ui_requirement_missing:{name}")
    return blockers
