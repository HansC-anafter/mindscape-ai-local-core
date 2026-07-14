"""Installed capability manifest catalog for Settings extensions."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.services.runtime_pack_hygiene import is_ignored_runtime_pack_dir
from backend.app.services.manifest_utils import resolve_tool_schema_paths

logger = logging.getLogger(__name__)


class ExactOwnerManifestError(RuntimeError):
    """Raised when an exact owner manifest is present but unsafe or malformed."""


def get_capabilities_dir() -> Path:
    """Return the installed capability directory."""
    return Path(__file__).resolve().parents[3] / "capabilities"


def get_installed_capabilities() -> List[str]:
    """Return installed capability codes discovered from manifest files."""
    capabilities: List[str] = []
    capabilities_dir = get_capabilities_dir()
    if not capabilities_dir.exists():
        logger.warning("Capabilities directory not found: %s", capabilities_dir)
        return capabilities

    for capability_dir in capabilities_dir.iterdir():
        if (
            not capability_dir.is_dir()
            or is_ignored_runtime_pack_dir(capability_dir.name)
        ):
            continue
        manifest_path = capability_dir / "manifest.yaml"
        if not manifest_path.exists():
            continue
        try:
            with manifest_path.open("r", encoding="utf-8") as manifest_file:
                manifest = yaml.safe_load(manifest_file)
            if isinstance(manifest, dict) and manifest.get("code"):
                capabilities.append(str(manifest["code"]))
        except Exception as exc:
            logger.warning(
                "Failed to parse manifest in %s: %s",
                capability_dir,
                exc,
            )
    return capabilities


def load_manifest(capability_code: str) -> Optional[Dict[str, Any]]:
    """Load one manifest for the generic discovery path."""
    manifest_path = get_capabilities_dir() / capability_code / "manifest.yaml"
    if not manifest_path.exists():
        return None
    try:
        with manifest_path.open("r", encoding="utf-8") as manifest_file:
            manifest = yaml.safe_load(manifest_file)
        if not isinstance(manifest, dict):
            return None
        resolve_tool_schema_paths(manifest, manifest_path.parent)
        return manifest
    except Exception as exc:
        logger.warning(
            "Failed to load manifest for %s: %s",
            capability_code,
            exc,
        )
        return None


def _require_descendant(path: Path, parent: Path) -> None:
    """Require a resolved path to remain within its resolved parent."""
    try:
        path.relative_to(parent)
    except ValueError as exc:
        raise ExactOwnerManifestError(
            "Exact owner manifest escapes the installed capability root"
        ) from exc


def load_exact_owner_manifest(
    capability_code: str,
) -> Optional[Dict[str, Any]]:
    """Load one exact installed manifest without scanning unrelated packs."""
    capabilities_dir = get_capabilities_dir()
    if not capabilities_dir.exists():
        return None

    try:
        resolved_root = capabilities_dir.resolve(strict=True)
        capability_path = capabilities_dir / capability_code
        if not capability_path.exists():
            return None
        resolved_capability = capability_path.resolve(strict=True)
        _require_descendant(resolved_capability, resolved_root)
        if (
            not resolved_capability.is_dir()
            or is_ignored_runtime_pack_dir(capability_path.name)
        ):
            return None

        manifest_path = resolved_capability / "manifest.yaml"
        if not manifest_path.exists():
            return None
        resolved_manifest = manifest_path.resolve(strict=True)
        _require_descendant(resolved_manifest, resolved_root)
        _require_descendant(resolved_manifest, resolved_capability)
        if not resolved_manifest.is_file():
            raise ExactOwnerManifestError(
                "Exact owner manifest is not a regular file"
            )

        with resolved_manifest.open("r", encoding="utf-8") as manifest_file:
            manifest = yaml.safe_load(manifest_file)
    except ExactOwnerManifestError:
        raise
    except (OSError, yaml.YAMLError) as exc:
        raise ExactOwnerManifestError(
            "Exact owner manifest could not be read"
        ) from exc

    if not isinstance(manifest, dict):
        raise ExactOwnerManifestError("Exact owner manifest must be an object")
    if manifest.get("code") != capability_code:
        raise ExactOwnerManifestError(
            "Exact owner manifest capability code does not match the query"
        )
    manifest["_file_path"] = str(resolved_manifest)
    return manifest
