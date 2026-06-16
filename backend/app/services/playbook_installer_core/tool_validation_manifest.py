"""Manifest and spec helpers for playbook tool validation."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import yaml

logger = logging.getLogger(f"{__package__}.tool_validation")


def _load_optional_python_packages(
    capabilities_dir: Path,
    capability_code: str,
) -> List[str]:
    """Read optional Python packages declared in the capability manifest."""
    possible_dir_names = [
        capability_code,
        capability_code.replace("_", "-"),
        capability_code.replace("-", "_"),
    ]
    for dir_name in possible_dir_names:
        manifest_path = capabilities_dir / dir_name / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            with open(manifest_path, "r", encoding="utf-8") as file:
                manifest = yaml.safe_load(file) or {}
            deps = manifest.get("dependencies", {})
            python_packages = deps.get("python_packages", {})
            optional_packages = python_packages.get("optional", [])
            if optional_packages:
                logger.debug(
                    f"Found optional Python packages in manifest: {optional_packages}"
                )
            return optional_packages
        except Exception as exc:
            logger.debug(
                f"Failed to read manifest for optional Python packages: {exc}"
            )
            return []
    return []


def _load_required_capabilities(specs_dir: Path, playbook_code: str) -> List[str]:
    """Read required capabilities from the installed playbook spec."""
    spec_path = specs_dir / f"{playbook_code}.json"
    if not spec_path.exists():
        return []
    try:
        with open(spec_path, "r", encoding="utf-8") as file:
            spec = json.load(file)
        return spec.get("required_capabilities", [])
    except Exception as exc:
        logger.warning(
            f"Failed to read playbook spec for required_capabilities: {exc}"
        )
        return []


def _get_backend_from_manifest(
    capabilities_dir: Path,
    manifest_tool_backends: Dict[str, Dict[str, str]],
    capability_name: str,
    tool_name: str,
) -> Optional[str]:
    """Resolve a tool backend from the capability manifest."""
    if capability_name in manifest_tool_backends:
        return manifest_tool_backends[capability_name].get(tool_name)

    manifest_tool_backends[capability_name] = {}
    possible_dirs = [
        capability_name,
        capability_name.replace("_", "-"),
        capability_name.replace("-", "_"),
    ]

    manifest_path = None
    for dir_name in possible_dirs:
        candidate_path = capabilities_dir / dir_name / "manifest.yaml"
        if candidate_path.exists():
            manifest_path = candidate_path
            break

    if manifest_path and manifest_path.exists():
        try:
            with open(manifest_path, "r", encoding="utf-8") as file:
                manifest = yaml.safe_load(file) or {}
            for tool_config in manifest.get("tools", []):
                if not isinstance(tool_config, dict):
                    continue
                code = tool_config.get("code") or tool_config.get("name")
                backend_path = tool_config.get("backend")
                if code and backend_path:
                    manifest_tool_backends[capability_name][code] = backend_path
                    logger.debug(
                        f"Found tool backend from manifest: {capability_name}.{code} -> {backend_path}"
                    )
        except Exception as exc:
            logger.warning(
                f"Failed to read manifest for capability {capability_name} from {manifest_path}: {exc}"
            )
    else:
        logger.debug(
            "Manifest not found for capability %s, tried paths: %s",
            capability_name,
            [str(capabilities_dir / dirname / "manifest.yaml") for dirname in possible_dirs],
        )

    return manifest_tool_backends[capability_name].get(tool_name)


def _is_optional_import_error(
    error_message: str, optional_python_packages: List[str]
) -> bool:
    """Determine whether an import failure should be downgraded to a warning."""
    if optional_python_packages:
        for package in optional_python_packages:
            if str(package).lower() in error_message.lower():
                return True

    fallback_markers = [
        "langchain",
        "asyncpg",
        "services.divi",
        "capabilities.wordpress",
        "database.models.divi",
    ]
    return any(marker in error_message.lower() for marker in fallback_markers)
