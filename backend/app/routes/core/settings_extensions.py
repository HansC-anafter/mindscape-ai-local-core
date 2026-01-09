"""
Settings Extensions API

API endpoint for retrieving Settings Extension Panels from installed capability packs.
Supports dynamic loading of UI components that extend the Settings page.
"""

import logging
import yaml
from pathlib import Path
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Query, HTTPException

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])


def get_installed_capabilities() -> List[str]:
    """
    Get list of installed capability codes.

    Returns:
        List of capability codes
    """
    try:
        from backend.app.capabilities.registry import get_capability_registry

        registry = get_capability_registry()
        return list(registry.get_all_capability_codes())
    except Exception as e:
        logger.warning(f"Failed to get capability registry: {e}")
        return []


def load_manifest(capability_code: str) -> Optional[Dict[str, Any]]:
    """
    Load manifest for a capability.

    Args:
        capability_code: Capability code

    Returns:
        Manifest dict or None if not found
    """
    try:
        from backend.app.capabilities.registry import get_capability_registry

        registry = get_capability_registry()
        capability = registry.get_capability(capability_code)
        if capability and hasattr(capability, 'manifest_path') and capability.manifest_path:
            manifest_path = Path(capability.manifest_path)
            if manifest_path.exists():
                with manifest_path.open('r', encoding='utf-8') as f:
                    return yaml.safe_load(f)
    except Exception as e:
        logger.warning(f"Failed to load manifest for {capability_code}: {e}")

    return None


def get_registered_runtime_codes() -> List[str]:
    """
    Get list of registered runtime codes.

    Returns:
        List of runtime codes
    """
    try:
        from backend.app.routes.core.runtime_environments import get_runtime_registry

        registry = get_runtime_registry()
        return [runtime.code for runtime in registry.get_all_runtimes()]
    except Exception as e:
        logger.warning(f"Failed to get runtime registry: {e}")
        return []


def get_registered_service_codes() -> List[str]:
    """
    Get list of registered service codes.

    Returns:
        List of service codes
    """
    try:
        from backend.app.services.tool_registry import get_tool_registry

        registry = get_tool_registry()
        services = []
        for tool in registry.get_all_tools():
            if hasattr(tool, 'service_code') and tool.service_code:
                services.append(tool.service_code)
        return list(set(services))
    except Exception as e:
        logger.warning(f"Failed to get service registry: {e}")
        return []


def check_show_when(show_when: Dict[str, Any]) -> bool:
    """
    Check if component should be shown based on show_when conditions.

    Args:
        show_when: show_when configuration dict

    Returns:
        True if component should be shown, False otherwise
    """
    if not show_when:
        return True

    if show_when.get("always"):
        return True

    if runtime_codes := show_when.get("runtime_codes"):
        registered_runtimes = get_registered_runtime_codes()
        return any(code in registered_runtimes for code in runtime_codes)

    if service_codes := show_when.get("service_codes"):
        registered_services = get_registered_service_codes()
        return any(code in registered_services for code in service_codes)

    return True


@router.get("/extensions")
async def get_settings_extensions(
    section: Optional[str] = Query(None, description="Filter by section")
) -> List[Dict[str, Any]]:
    """
    Get all Settings Extension Panels from installed capability packs.

    Scans installed capabilities and collects UI components with settings configuration.
    Supports section filtering and show_when condition checking.

    Args:
        section: Optional section filter (e.g., "runtime-environments", "external-services")

    Returns:
        List of extension panel definitions
    """
    extensions = []

    try:
        installed_capabilities = get_installed_capabilities()

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
                if not check_show_when(show_when):
                    continue

                component_code = component.get("code")
                component_path = component.get("path", "")

                import_path = f"@/app/capabilities/{capability_code}/components/{Path(component_path).name}"
                if component_path.startswith("ui/"):
                    import_path = f"@/app/capabilities/{capability_code}/components/{Path(component_path).name}"

                extension = {
                    "capability_code": capability_code,
                    "component_code": component_code,
                    "import_path": import_path,
                    "export": component.get("export", "default"),
                    "section": component_section,
                    "title": settings_config.get("title", component_code),
                    "order": settings_config.get("order", 100),
                    "requires_workspace_id": settings_config.get("requires_workspace_id", False),
                    "show_when": show_when,
                }

                extensions.append(extension)

        extensions.sort(key=lambda x: x["order"])

    except Exception as e:
        logger.error(f"Failed to get settings extensions: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get settings extensions: {str(e)}")

    return extensions
