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

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


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
        if not cap_dir.is_dir() or cap_dir.name.startswith("_"):
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
                return yaml.safe_load(f)
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
        return [r.id for r in runtimes if r.id]
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

        # Pre-fetch registered codes for show_when logic
        registered_runtimes = get_registered_runtime_codes(db)
        registered_services = get_registered_service_codes(db)

        for capability_code in installed_capabilities:
            manifest = load_manifest(capability_code)
            if not manifest:
                continue

            ui_components = manifest.get("ui_components", [])

            for component in ui_components:
                settings_config = component.get("settings")
                if not settings_config:
                    continue

                component_section = settings_config.get("section")

                if section and component_section != section:
                    continue

                show_when = settings_config.get("show_when", {})
                if not check_show_when(
                    show_when, registered_runtimes, registered_services
                ):
                    continue

                component_code = component.get("code")
                component_path = component.get("path", "")

                # Map manifest source path to installed path
                # Per CAPABILITY_INSTALLATION_GUIDE.md:
                #   ui/components/X.tsx -> components/X.tsx  (remove components/ prefix)
                #   ui/X.tsx           -> components/X.tsx   (default to components/)
                # Import path: @/app/capabilities/{code}/components/{Name}
                if component_path.startswith("ui/components/"):
                    # e.g. "ui/components/Panel.tsx" -> "components/Panel.tsx"
                    installed_path = (
                        "components/" + component_path[len("ui/components/") :]
                    )
                elif component_path.startswith("ui/"):
                    # e.g. "ui/Panel.tsx" -> "components/Panel.tsx"
                    installed_path = "components/" + component_path[len("ui/") :]
                else:
                    installed_path = component_path

                import_path = f"@/app/capabilities/{capability_code}/{installed_path}"
                # Strip .tsx/.ts extension per spec
                for ext in (".tsx", ".ts", ".jsx", ".js"):
                    if import_path.endswith(ext):
                        import_path = import_path[: -len(ext)]
                        break

                extension = {
                    "capability_code": capability_code,
                    "component_code": component_code,
                    "import_path": import_path,
                    "export": component.get("export", "default"),
                    "section": component_section,
                    "title": settings_config.get("title", component_code),
                    "order": settings_config.get("order", 100),
                    "requires_workspace_id": settings_config.get(
                        "requires_workspace_id", False
                    ),
                    "show_when": show_when,
                }

                extensions.append(extension)

        extensions.sort(key=lambda x: x["order"])

    except Exception as e:
        logger.error(f"Failed to get settings extensions: {e}", exc_info=True)
        return []

    return extensions
