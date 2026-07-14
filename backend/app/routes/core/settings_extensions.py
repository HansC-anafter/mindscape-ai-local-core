"""
Settings Extensions API Routes

Discovers and registers settings panels from installed capability packs.
Supports dynamic loading of UI components that extend the Settings page.
"""

import logging
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text

from backend.app.database.session import get_db_postgres as get_db
from backend.app.models.runtime_environment import RuntimeEnvironment
from app.services.runtime_pack_hygiene import is_ignored_runtime_pack_dir
from .capability_packs_core.installed_routes import _get_runtime_ui_component

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

_BUILT_IN_RUNTIME_CODES = {
    "local-core",
    "local_core",
    "blender-bridge-mesh",
    "blender_bridge_mesh",
    "blender_bridge",
}


def _slugify_runtime_code(value: Any) -> Optional[str]:
    text = str(value or "").strip().lower()
    if not text:
        return None
    normalized = "".join(ch if ch.isalnum() else "_" for ch in text)
    normalized = "_".join(segment for segment in normalized.split("_") if segment)
    return normalized or None


def _get_capabilities_dir() -> Path:
    """Get the capabilities directory path."""
    return Path(__file__).parent.parent.parent / "capabilities"


def get_installed_capabilities() -> List[str]:
    """
    Get list of installed capability codes by scanning capabilities directory.

    Returns:
        List of capability codes
    """
    capabilities = []
    caps_dir = _get_capabilities_dir()
    if not caps_dir.exists():
        logger.warning(f"Capabilities directory not found: {caps_dir}")
        return []

    for cap_dir in caps_dir.iterdir():
        if not cap_dir.is_dir() or is_ignored_runtime_pack_dir(cap_dir.name):
            continue
        manifest_path = cap_dir / "manifest.yaml"
        if manifest_path.exists():
            try:
                with manifest_path.open("r", encoding="utf-8") as f:
                    manifest = yaml.safe_load(f)
                code = manifest.get("code")
                if code:
                    capabilities.append(code)
            except Exception as e:
                logger.warning(f"Failed to parse manifest in {cap_dir}: {e}")
    return capabilities


def load_manifest(capability_code: str) -> Optional[Dict[str, Any]]:
    """
    Load manifest for a capability from filesystem.

    Args:
        capability_code: Capability code

    Returns:
        Manifest dict or None if not found
    """
    caps_dir = _get_capabilities_dir()
    manifest_path = caps_dir / capability_code / "manifest.yaml"
    if manifest_path.exists():
        try:
            with manifest_path.open("r", encoding="utf-8") as f:
                manifest = yaml.safe_load(f)
            if manifest:
                from backend.app.services.manifest_utils import (
                    resolve_tool_schema_paths,
                )

                resolve_tool_schema_paths(manifest, manifest_path.parent)
            return manifest
        except Exception as e:
            logger.warning(f"Failed to load manifest for {capability_code}: {e}")
    return None


def get_registered_runtime_codes(db: Session) -> List[str]:
    """
    Get list of registered runtime codes from database.

    Args:
        db: Database session

    Returns:
        List of runtime codes
    """
    try:
        runtimes = db.query(RuntimeEnvironment).all()
        codes = set(_BUILT_IN_RUNTIME_CODES)
        for runtime in runtimes:
            metadata = runtime.extra_metadata or {}
            for value in (
                runtime.id,
                _slugify_runtime_code(runtime.id),
                runtime.name,
                _slugify_runtime_code(runtime.name),
                metadata.get("runtime_type"),
                _slugify_runtime_code(metadata.get("runtime_type")),
                metadata.get("capability_code"),
                _slugify_runtime_code(metadata.get("capability_code")),
            ):
                if value:
                    codes.add(value)
        return list(codes)
    except Exception as e:
        logger.warning(f"Failed to get runtimes from DB: {e}")
        return []


def get_registered_service_codes(db: Session) -> List[str]:
    """
    Get list of registered service codes from database.

    Args:
        db: Database session

    Returns:
        List of service codes
    """
    try:
        # Use raw SQL because RegisteredTool is a Pydantic model (manual mapping)
        result = db.execute(
            text("SELECT DISTINCT provider, capability_code FROM tool_registry")
        )
        codes = set()
        for row in result:
            if row.provider:
                codes.add(row.provider)
            if row.capability_code:
                codes.add(row.capability_code)
        return list(codes)
    except Exception as e:
        logger.warning(f"Failed to get services from DB: {e}")
        return []


def check_show_when(
    show_when: Dict[str, Any],
    registered_runtimes: List[str],
    registered_services: List[str],
) -> bool:
    """
    Check if component should be shown based on show_when conditions.

    Args:
        show_when: show_when configuration dict
        registered_runtimes: List of available runtime codes
        registered_services: List of available service codes

    Returns:
        True if component should be shown, False otherwise
    """
    if not show_when:
        return True

    if show_when.get("always"):
        return True

    if runtime_codes := show_when.get("runtime_codes"):
        return any(code in registered_runtimes for code in runtime_codes)

    if service_codes := show_when.get("service_codes"):
        return any(code in registered_services for code in service_codes)

    return True


@router.get("/extensions")
async def get_settings_extensions(
    section: Optional[str] = Query(None, description="Filter by section"),
    workspace_id: Optional[str] = Query(None, description="Workspace ID for workspace-scoped settings panels"),
    db: Session = Depends(get_db),
) -> List[Dict[str, Any]]:
    """
    Get all Settings Extension Panels from installed capability packs.

    Scans installed capabilities and collects UI components with settings configuration.
    Supports section filtering and show_when condition checking.

    Args:
        section: Optional section filter (e.g., "runtime-environments", "external-services")
        db: Database session

    Returns:
        List of extension panel definitions
    """
    extensions = []

    try:
        installed_capabilities = get_installed_capabilities()
        candidates = []

        for capability_code in installed_capabilities:
            manifest = load_manifest(capability_code)
            if not manifest:
                continue

            ui_components = manifest.get("ui_components", [])
            if not isinstance(ui_components, list):
                logger.warning(
                    "Ignoring malformed ui_components for capability %s",
                    capability_code,
                )
                continue

            for component in ui_components:
                if not isinstance(component, dict):
                    logger.warning(
                        "Ignoring malformed settings component for capability %s",
                        capability_code,
                    )
                    continue
                settings_config = component.get("settings")
                if not isinstance(settings_config, dict):
                    continue

                component_section = settings_config.get("section")

                if section and component_section != section:
                    continue

                requires_workspace_id = bool(
                    settings_config.get("requires_workspace_id")
                )
                if workspace_id and not requires_workspace_id:
                    continue
                if requires_workspace_id and not workspace_id:
                    continue

                show_when = settings_config.get("show_when", {})
                candidates.append(
                    (capability_code, component, settings_config, show_when)
                )

        needs_runtime_codes = any(
            not show_when.get("always") and show_when.get("runtime_codes")
            for *_, show_when in candidates
        )
        needs_service_codes = any(
            not show_when.get("always")
            and not show_when.get("runtime_codes")
            and show_when.get("service_codes")
            for *_, show_when in candidates
        )
        registered_runtimes = (
            get_registered_runtime_codes(db) if needs_runtime_codes else []
        )
        registered_services = (
            get_registered_service_codes(db) if needs_service_codes else []
        )

        for capability_code, component, settings_config, show_when in candidates:
            if not check_show_when(
                show_when, registered_runtimes, registered_services
            ):
                continue

            component_code = component.get("code")
            component_path = component.get("path", "")
            component_section = settings_config.get("section")

            # Map manifest source paths to installed capability component paths.
            if component_path.startswith("ui/components/"):
                installed_path = (
                    "components/" + component_path[len("ui/components/") :]
                )
            elif component_path.startswith("ui/"):
                installed_path = "components/" + component_path[len("ui/") :]
            else:
                installed_path = component_path

            import_path = f"@/app/capabilities/{capability_code}/{installed_path}"
            for ext in (".tsx", ".ts", ".jsx", ".js"):
                if import_path.endswith(ext):
                    import_path = import_path[: -len(ext)]
                    break

            extension = {
                "capability_code": capability_code,
                "component_code": component_code,
                "path": component_path,
                "import_path": import_path,
                "export": component.get("export", "default"),
                "section": component_section,
                "title": settings_config.get("title", component_code),
                "description": settings_config.get("description")
                or component.get("description"),
                "order": settings_config.get("order", 100),
                "requires_workspace_id": bool(
                    settings_config.get("requires_workspace_id")
                ),
                "display_mode": settings_config.get("display_mode"),
                "show_when": show_when,
                "props_schema": settings_config.get("props_schema"),
                "legacy_context": component.get("legacy_context"),
            }
            runtime_component = _get_runtime_ui_component(
                capability_code,
                component_code,
                strict=True,
            )
            for field_name in (
                "asset_url",
                "integrity",
                "bytes",
                "runtime",
                "asset_path",
            ):
                if runtime_component.get(field_name) is not None:
                    extension[field_name] = runtime_component[field_name]
            if runtime_component.get("export"):
                extension["export"] = runtime_component["export"]

            extensions.append(extension)

        extensions.sort(key=lambda x: x["order"])

    except Exception as e:
        logger.error(f"Failed to get settings extensions: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="settings_extensions_unavailable",
        ) from e

    return extensions
