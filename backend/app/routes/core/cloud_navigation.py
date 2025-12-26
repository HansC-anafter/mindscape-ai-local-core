"""
Backend proxy for Cloud navigation endpoints (deprecated for UI components).
UI components should be installed via CapabilityInstaller and loaded directly from frontend.
This module may still be used for other Cloud navigation purposes (if any).
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from ...services.system_settings_store import SystemSettingsStore
from ...capabilities.api_loader import CapabilityAPILoader
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cloud-navigation", tags=["cloud-navigation"])

settings_store = SystemSettingsStore()
api_loader = CapabilityAPILoader()


def get_cloud_frontend_url() -> Optional[str]:
    """
    Get Cloud frontend URL from system settings.

    Returns:
        Cloud frontend URL or None if not configured
    """
    cloud_frontend_url = settings_store.get("cloud_frontend_url", default="")
    if cloud_frontend_url:
        return cloud_frontend_url
    return None


def load_capability_manifest(capability_code: str) -> Optional[Dict[str, Any]]:
    """
    Load capability pack manifest from Cloud capabilities directory.

    Args:
        capability_code: Capability code (e.g., 'ig')

    Returns:
        Manifest dict or None if not found
    """
    try:
        # Get remote capabilities directory from SystemSettingsStore or CapabilityAPILoader instance
        # Priority: 1) SystemSettingsStore, 2) CapabilityAPILoader instance's remote_capabilities_dir
        remote_capabilities_dir_str = settings_store.get("remote_capabilities_dir", default="")

        if remote_capabilities_dir_str:
            cloud_capabilities_dir = Path(remote_capabilities_dir_str)
        elif api_loader.remote_capabilities_dir and api_loader.remote_capabilities_dir.exists():
            cloud_capabilities_dir = api_loader.remote_capabilities_dir
        else:
            logger.debug("Remote capabilities directory not configured")
            return None

        if not cloud_capabilities_dir.exists():
            logger.debug(f"Remote capabilities directory does not exist: {cloud_capabilities_dir}")
            return None

        manifest_path = cloud_capabilities_dir / capability_code / "manifest.yaml"
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            logger.debug(f"Manifest not found at {manifest_path}")
            return None
    except Exception as e:
        logger.error(f"Failed to load manifest for {capability_code}: {e}")
        return None


def get_ui_component_route(capability_code: str, artifact_type: Optional[str] = None, playbook_code: Optional[str] = None) -> Optional[str]:
    """
    Get UI component route from capability pack manifest.

    Args:
        capability_code: Capability code (e.g., 'ig')
        artifact_type: Artifact type to match (e.g., 'ig_posts')
        playbook_code: Playbook code to match (e.g., 'ig_post_generation')

    Returns:
        UI component route template or None if not found
    """
    manifest = load_capability_manifest(capability_code)
    if not manifest:
        return None

    ui_components = manifest.get("ui_components", [])
    for component in ui_components:
        # Check if component matches artifact_type or playbook_code
        artifact_types = component.get("artifact_types", [])
        playbook_codes = component.get("playbook_codes", [])

        matches = True
        if artifact_type and artifact_types:
            matches = matches and artifact_type in artifact_types
        if playbook_code and playbook_codes:
            matches = matches and playbook_code in playbook_codes

        # If no filters specified, or if matches, return the route
        if (not artifact_types and not playbook_codes) or matches:
            route = component.get("route")
            if route:
                return route

    return None


@router.get("/frontend-url")
async def get_frontend_url():
    """
    Get Cloud frontend URL for navigation.

    Returns:
        JSON with cloud_frontend_url
    """
    try:
        url = get_cloud_frontend_url()
        if not url:
            raise HTTPException(
                status_code=404,
                detail="Cloud frontend URL not configured. Please set cloud_frontend_url in system settings."
            )
        return {"cloud_frontend_url": url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Cloud frontend URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Cloud frontend URL")


@router.get("/ui-route")
async def get_ui_route(
    capability_code: str = Query(..., description="Capability code (e.g., 'ig')"),
    artifact_type: Optional[str] = Query(None, description="Artifact type to match"),
    playbook_code: Optional[str] = Query(None, description="Playbook code to match")
):
    """
    Get UI component route from capability pack definition.

    Args:
        capability_code: Capability code
        artifact_type: Optional artifact type filter
        playbook_code: Optional playbook code filter

    Returns:
        JSON with ui_route template
    """
    try:
        route = get_ui_component_route(capability_code, artifact_type, playbook_code)
        if route:
            return {"ui_route": route}
        else:
            raise HTTPException(
                status_code=404,
                detail=f"UI component route not found for capability '{capability_code}'"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get UI route: {e}")
        raise HTTPException(status_code=500, detail="Failed to get UI route")


@router.get("/redirect/{workspace_id}")
async def redirect_to_ui_component(
    workspace_id: str,
    capability_code: str = Query(..., description="Capability code (e.g., 'ig')"),
    artifact_type: Optional[str] = Query(None, description="Artifact type to match"),
    playbook_code: Optional[str] = Query(None, description="Playbook code to match")
):
    """
    Redirect to Cloud UI component page based on capability pack definition.

    Args:
        workspace_id: Workspace ID
        capability_code: Capability code
        artifact_type: Optional artifact type filter
        playbook_code: Optional playbook code filter

    Returns:
        Redirect response to Cloud frontend UI component page
    """
    try:
        route_template = get_ui_component_route(capability_code, artifact_type, playbook_code)
        if not route_template:
            raise HTTPException(
                status_code=404,
                detail=f"UI component route not found for capability '{capability_code}'"
            )

        # Replace template variables
        route = route_template.replace("{workspace_id}", workspace_id)

        cloud_frontend_url = get_cloud_frontend_url()
        if not cloud_frontend_url:
            raise HTTPException(
                status_code=404,
                detail="Cloud frontend URL not configured. Please set cloud_frontend_url in system settings."
            )
        redirect_url = f"{cloud_frontend_url}{route}"
        return RedirectResponse(url=redirect_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to redirect to UI component: {e}")
        raise HTTPException(status_code=500, detail="Failed to redirect to UI component")


UI components should be installed via CapabilityInstaller and loaded directly from frontend.
This module may still be used for other Cloud navigation purposes (if any).
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from ...services.system_settings_store import SystemSettingsStore
from ...capabilities.api_loader import CapabilityAPILoader
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cloud-navigation", tags=["cloud-navigation"])

settings_store = SystemSettingsStore()
api_loader = CapabilityAPILoader()


def get_cloud_frontend_url() -> Optional[str]:
    """
    Get Cloud frontend URL from system settings.

    Returns:
        Cloud frontend URL or None if not configured
    """
    cloud_frontend_url = settings_store.get("cloud_frontend_url", default="")
    if cloud_frontend_url:
        return cloud_frontend_url
    return None


def load_capability_manifest(capability_code: str) -> Optional[Dict[str, Any]]:
    """
    Load capability pack manifest from Cloud capabilities directory.

    Args:
        capability_code: Capability code (e.g., 'ig')

    Returns:
        Manifest dict or None if not found
    """
    try:
        # Get remote capabilities directory from SystemSettingsStore or CapabilityAPILoader instance
        # Priority: 1) SystemSettingsStore, 2) CapabilityAPILoader instance's remote_capabilities_dir
        remote_capabilities_dir_str = settings_store.get("remote_capabilities_dir", default="")

        if remote_capabilities_dir_str:
            cloud_capabilities_dir = Path(remote_capabilities_dir_str)
        elif api_loader.remote_capabilities_dir and api_loader.remote_capabilities_dir.exists():
            cloud_capabilities_dir = api_loader.remote_capabilities_dir
        else:
            logger.debug("Remote capabilities directory not configured")
            return None

        if not cloud_capabilities_dir.exists():
            logger.debug(f"Remote capabilities directory does not exist: {cloud_capabilities_dir}")
            return None

        manifest_path = cloud_capabilities_dir / capability_code / "manifest.yaml"
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            logger.debug(f"Manifest not found at {manifest_path}")
            return None
    except Exception as e:
        logger.error(f"Failed to load manifest for {capability_code}: {e}")
        return None


def get_ui_component_route(capability_code: str, artifact_type: Optional[str] = None, playbook_code: Optional[str] = None) -> Optional[str]:
    """
    Get UI component route from capability pack manifest.

    Args:
        capability_code: Capability code (e.g., 'ig')
        artifact_type: Artifact type to match (e.g., 'ig_posts')
        playbook_code: Playbook code to match (e.g., 'ig_post_generation')

    Returns:
        UI component route template or None if not found
    """
    manifest = load_capability_manifest(capability_code)
    if not manifest:
        return None

    ui_components = manifest.get("ui_components", [])
    for component in ui_components:
        # Check if component matches artifact_type or playbook_code
        artifact_types = component.get("artifact_types", [])
        playbook_codes = component.get("playbook_codes", [])

        matches = True
        if artifact_type and artifact_types:
            matches = matches and artifact_type in artifact_types
        if playbook_code and playbook_codes:
            matches = matches and playbook_code in playbook_codes

        # If no filters specified, or if matches, return the route
        if (not artifact_types and not playbook_codes) or matches:
            route = component.get("route")
            if route:
                return route

    return None


@router.get("/frontend-url")
async def get_frontend_url():
    """
    Get Cloud frontend URL for navigation.

    Returns:
        JSON with cloud_frontend_url
    """
    try:
        url = get_cloud_frontend_url()
        if not url:
            raise HTTPException(
                status_code=404,
                detail="Cloud frontend URL not configured. Please set cloud_frontend_url in system settings."
            )
        return {"cloud_frontend_url": url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Cloud frontend URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Cloud frontend URL")


@router.get("/ui-route")
async def get_ui_route(
    capability_code: str = Query(..., description="Capability code (e.g., 'ig')"),
    artifact_type: Optional[str] = Query(None, description="Artifact type to match"),
    playbook_code: Optional[str] = Query(None, description="Playbook code to match")
):
    """
    Get UI component route from capability pack definition.

    Args:
        capability_code: Capability code
        artifact_type: Optional artifact type filter
        playbook_code: Optional playbook code filter

    Returns:
        JSON with ui_route template
    """
    try:
        route = get_ui_component_route(capability_code, artifact_type, playbook_code)
        if route:
            return {"ui_route": route}
        else:
            raise HTTPException(
                status_code=404,
                detail=f"UI component route not found for capability '{capability_code}'"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get UI route: {e}")
        raise HTTPException(status_code=500, detail="Failed to get UI route")


@router.get("/redirect/{workspace_id}")
async def redirect_to_ui_component(
    workspace_id: str,
    capability_code: str = Query(..., description="Capability code (e.g., 'ig')"),
    artifact_type: Optional[str] = Query(None, description="Artifact type to match"),
    playbook_code: Optional[str] = Query(None, description="Playbook code to match")
):
    """
    Redirect to Cloud UI component page based on capability pack definition.

    Args:
        workspace_id: Workspace ID
        capability_code: Capability code
        artifact_type: Optional artifact type filter
        playbook_code: Optional playbook code filter

    Returns:
        Redirect response to Cloud frontend UI component page
    """
    try:
        route_template = get_ui_component_route(capability_code, artifact_type, playbook_code)
        if not route_template:
            raise HTTPException(
                status_code=404,
                detail=f"UI component route not found for capability '{capability_code}'"
            )

        # Replace template variables
        route = route_template.replace("{workspace_id}", workspace_id)

        cloud_frontend_url = get_cloud_frontend_url()
        if not cloud_frontend_url:
            raise HTTPException(
                status_code=404,
                detail="Cloud frontend URL not configured. Please set cloud_frontend_url in system settings."
            )
        redirect_url = f"{cloud_frontend_url}{route}"
        return RedirectResponse(url=redirect_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to redirect to UI component: {e}")
        raise HTTPException(status_code=500, detail="Failed to redirect to UI component")


UI components should be installed via CapabilityInstaller and loaded directly from frontend.
This module may still be used for other Cloud navigation purposes (if any).
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from ...services.system_settings_store import SystemSettingsStore
from ...capabilities.api_loader import CapabilityAPILoader
import yaml
from pathlib import Path
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/cloud-navigation", tags=["cloud-navigation"])

settings_store = SystemSettingsStore()
api_loader = CapabilityAPILoader()


def get_cloud_frontend_url() -> Optional[str]:
    """
    Get Cloud frontend URL from system settings.

    Returns:
        Cloud frontend URL or None if not configured
    """
    cloud_frontend_url = settings_store.get("cloud_frontend_url", default="")
    if cloud_frontend_url:
        return cloud_frontend_url
    return None


def load_capability_manifest(capability_code: str) -> Optional[Dict[str, Any]]:
    """
    Load capability pack manifest from Cloud capabilities directory.

    Args:
        capability_code: Capability code (e.g., 'ig')

    Returns:
        Manifest dict or None if not found
    """
    try:
        # Get remote capabilities directory from SystemSettingsStore or CapabilityAPILoader instance
        # Priority: 1) SystemSettingsStore, 2) CapabilityAPILoader instance's remote_capabilities_dir
        remote_capabilities_dir_str = settings_store.get("remote_capabilities_dir", default="")

        if remote_capabilities_dir_str:
            cloud_capabilities_dir = Path(remote_capabilities_dir_str)
        elif api_loader.remote_capabilities_dir and api_loader.remote_capabilities_dir.exists():
            cloud_capabilities_dir = api_loader.remote_capabilities_dir
        else:
            logger.debug("Remote capabilities directory not configured")
            return None

        if not cloud_capabilities_dir.exists():
            logger.debug(f"Remote capabilities directory does not exist: {cloud_capabilities_dir}")
            return None

        manifest_path = cloud_capabilities_dir / capability_code / "manifest.yaml"
        if manifest_path.exists():
            with open(manifest_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            logger.debug(f"Manifest not found at {manifest_path}")
            return None
    except Exception as e:
        logger.error(f"Failed to load manifest for {capability_code}: {e}")
        return None


def get_ui_component_route(capability_code: str, artifact_type: Optional[str] = None, playbook_code: Optional[str] = None) -> Optional[str]:
    """
    Get UI component route from capability pack manifest.

    Args:
        capability_code: Capability code (e.g., 'ig')
        artifact_type: Artifact type to match (e.g., 'ig_posts')
        playbook_code: Playbook code to match (e.g., 'ig_post_generation')

    Returns:
        UI component route template or None if not found
    """
    manifest = load_capability_manifest(capability_code)
    if not manifest:
        return None

    ui_components = manifest.get("ui_components", [])
    for component in ui_components:
        # Check if component matches artifact_type or playbook_code
        artifact_types = component.get("artifact_types", [])
        playbook_codes = component.get("playbook_codes", [])

        matches = True
        if artifact_type and artifact_types:
            matches = matches and artifact_type in artifact_types
        if playbook_code and playbook_codes:
            matches = matches and playbook_code in playbook_codes

        # If no filters specified, or if matches, return the route
        if (not artifact_types and not playbook_codes) or matches:
            route = component.get("route")
            if route:
                return route

    return None


@router.get("/frontend-url")
async def get_frontend_url():
    """
    Get Cloud frontend URL for navigation.

    Returns:
        JSON with cloud_frontend_url
    """
    try:
        url = get_cloud_frontend_url()
        if not url:
            raise HTTPException(
                status_code=404,
                detail="Cloud frontend URL not configured. Please set cloud_frontend_url in system settings."
            )
        return {"cloud_frontend_url": url}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Cloud frontend URL: {e}")
        raise HTTPException(status_code=500, detail="Failed to get Cloud frontend URL")


@router.get("/ui-route")
async def get_ui_route(
    capability_code: str = Query(..., description="Capability code (e.g., 'ig')"),
    artifact_type: Optional[str] = Query(None, description="Artifact type to match"),
    playbook_code: Optional[str] = Query(None, description="Playbook code to match")
):
    """
    Get UI component route from capability pack definition.

    Args:
        capability_code: Capability code
        artifact_type: Optional artifact type filter
        playbook_code: Optional playbook code filter

    Returns:
        JSON with ui_route template
    """
    try:
        route = get_ui_component_route(capability_code, artifact_type, playbook_code)
        if route:
            return {"ui_route": route}
        else:
            raise HTTPException(
                status_code=404,
                detail=f"UI component route not found for capability '{capability_code}'"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get UI route: {e}")
        raise HTTPException(status_code=500, detail="Failed to get UI route")


@router.get("/redirect/{workspace_id}")
async def redirect_to_ui_component(
    workspace_id: str,
    capability_code: str = Query(..., description="Capability code (e.g., 'ig')"),
    artifact_type: Optional[str] = Query(None, description="Artifact type to match"),
    playbook_code: Optional[str] = Query(None, description="Playbook code to match")
):
    """
    Redirect to Cloud UI component page based on capability pack definition.

    Args:
        workspace_id: Workspace ID
        capability_code: Capability code
        artifact_type: Optional artifact type filter
        playbook_code: Optional playbook code filter

    Returns:
        Redirect response to Cloud frontend UI component page
    """
    try:
        route_template = get_ui_component_route(capability_code, artifact_type, playbook_code)
        if not route_template:
            raise HTTPException(
                status_code=404,
                detail=f"UI component route not found for capability '{capability_code}'"
            )

        # Replace template variables
        route = route_template.replace("{workspace_id}", workspace_id)

        cloud_frontend_url = get_cloud_frontend_url()
        if not cloud_frontend_url:
            raise HTTPException(
                status_code=404,
                detail="Cloud frontend URL not configured. Please set cloud_frontend_url in system settings."
            )
        redirect_url = f"{cloud_frontend_url}{route}"
        return RedirectResponse(url=redirect_url)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to redirect to UI component: {e}")
        raise HTTPException(status_code=500, detail="Failed to redirect to UI component")

