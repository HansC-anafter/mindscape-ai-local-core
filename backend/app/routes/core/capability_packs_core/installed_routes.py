import logging
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from .manifest_scan import (
    _WORKSPACE_TOOL_ID_PATTERN,
    _format_installed_capability,
    _get_installed_pack_ids,
    _get_pack_meta_by_code,
    _scan_pack_yaml_files,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/installed-capabilities")
def list_installed_capabilities():
    """
    List all installed capability packs with detailed information

    Returns list of installed packs with their metadata.
    This endpoint is used by the frontend to display installed capabilities.
    """
    t0 = time.time()
    logger.debug("list_installed_capabilities started")
    try:
        # Get all packs
        pack_metas = _scan_pack_yaml_files()
        t1 = time.time()
        logger.debug("Scanned capability manifests in %.3fs", t1 - t0)

        # Get installed pack IDs
        installed_ids = _get_installed_pack_ids()
        t2 = time.time()
        logger.debug("Loaded installed pack IDs in %.3fs", t2 - t1)

        # Filter to only installed packs and format response
        installed_capabilities = []
        for pack_meta in pack_metas:
            pack_id = pack_meta.get("id")
            if pack_id and pack_id in installed_ids:
                installed_capabilities.append(_format_installed_capability(pack_meta))

        t3 = time.time()
        logger.debug("Mapped installed capabilities in %.3fs", t3 - t2)
        logger.debug("Returning installed capabilities in %.3fs", t3 - t0)
        return JSONResponse(content=installed_capabilities)
    except Exception as e:
        logger.error(f"Failed to list installed capabilities: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list installed capabilities: {str(e)}"
        )


@router.get("/installed-capabilities/{capability_code}")
def get_installed_capability(capability_code: str):
    try:
        pack_meta = _get_pack_meta_by_code(capability_code)
        if not pack_meta:
            raise HTTPException(
                status_code=404, detail=f"Capability '{capability_code}' not found"
            )

        installed_ids = _get_installed_pack_ids()
        pack_id = pack_meta.get("id")
        if pack_id not in installed_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Capability '{capability_code}' is not installed",
            )

        return JSONResponse(content=_format_installed_capability(pack_meta))
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get installed capability %s: %s", capability_code, e, exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get installed capability: {str(e)}",
        )


@router.get(
    "/installed-capabilities/{capability_code}/ui-components",
    response_model=List[Dict[str, Any]],
)
def get_capability_ui_components(capability_code: str):
    """
    Get UI components information for an installed capability

    Returns UI components metadata from the capability's manifest.
    Frontend uses this to dynamically load UI components.

    Boundary: This API only reads manifest metadata, does not serve component code.
    Component code must be installed via RuntimeAssetsInstaller, not hardcoded.
    """
    try:
        pack_meta = _get_pack_meta_by_code(capability_code)
        if not pack_meta:
            raise HTTPException(
                status_code=404, detail=f"Capability '{capability_code}' not found"
            )

        installed_ids = _get_installed_pack_ids()
        pack_id = pack_meta.get("id")
        if pack_id not in installed_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Capability '{capability_code}' (pack_id: {pack_id}) is not installed",
            )

        # Return UI components from manifest
        ui_components = pack_meta.get("ui_components", [])

        formatted_components = [
            _format_ui_component_for_response(capability_code, component)
            for component in ui_components
        ]

        return formatted_components
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            f"Failed to get UI components for capability {capability_code}: {e}",
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get UI components: {str(e)}"
        )


def _format_ui_component_for_response(
    capability_code: str,
    component: Dict[str, Any],
) -> Dict[str, Any]:
    component_path = component.get("path", "")
    component_filename = Path(component_path).name
    component_name = component_filename.replace(".tsx", "").replace(".ts", "")
    path_parts = component_path.split("/")
    subdirectory = "components"
    if len(path_parts) >= 3 and path_parts[0] == "ui":
        subdirectory = path_parts[1]
    import_path = f"@/app/capabilities/{capability_code}/{subdirectory}/{component_name}"
    return {
        "code": component.get("code"),
        "path": component_path,
        "description": component.get("description", ""),
        "export": component.get("export", "default"),
        "artifact_types": component.get("artifact_types", []),
        "playbook_codes": component.get("playbook_codes", []),
        "import_path": import_path,
        "layout_hint": component.get("layout_hint", "default"),
    }


@router.get(
    "/installed-capabilities/{capability_code}/workspace-tools",
    response_model=List[Dict[str, Any]],
)
def get_capability_workspace_tools(capability_code: str):
    try:
        pack_meta = _get_pack_meta_by_code(capability_code)
        if not pack_meta:
            raise HTTPException(
                status_code=404, detail=f"Capability '{capability_code}' not found"
            )

        installed_ids = _get_installed_pack_ids()
        pack_id = pack_meta.get("id")
        if pack_id not in installed_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Capability '{capability_code}' (pack_id: {pack_id}) is not installed",
            )

        ui_components = pack_meta.get("ui_components", [])
        components_by_code = {
            component.get("code"): component
            for component in ui_components
            if isinstance(component, dict) and component.get("code")
        }
        formatted_tools = []
        seen_ids = set()
        for index, tool in enumerate(pack_meta.get("workspace_tools", []) or []):
            if not isinstance(tool, dict):
                raise HTTPException(
                    status_code=422,
                    detail=f"workspace_tools[{index}] must be an object",
                )
            tool_id = str(tool.get("id") or "").strip()
            group = str(tool.get("group") or "").strip()
            label = tool.get("label")
            icon = tool.get("icon")
            panel_component_code = str(tool.get("panel_component_code") or "").strip()
            order = tool.get("order")
            if not _WORKSPACE_TOOL_ID_PATTERN.match(tool_id) or tool_id in seen_ids:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"workspace_tools[{index}].id must match ^[a-z0-9_]+$ "
                        "and be unique"
                    ),
                )
            if group != "capability":
                raise HTTPException(
                    status_code=422,
                    detail=f"workspace_tools[{index}].group must be capability",
                )
            if not isinstance(label, str) or not label.strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"workspace_tools[{index}].label must be a non-empty string",
                )
            if not isinstance(icon, str) or not icon.strip():
                raise HTTPException(
                    status_code=422,
                    detail=f"workspace_tools[{index}].icon must be a non-empty string",
                )
            if type(order) is not int:
                raise HTTPException(
                    status_code=422,
                    detail=f"workspace_tools[{index}].order must be an integer",
                )
            panel_component = components_by_code.get(panel_component_code)
            if not panel_component:
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"workspace_tools[{index}].panel_component_code "
                        f"'{panel_component_code}' does not match ui_components[].code"
                    ),
                )
            seen_ids.add(tool_id)
            formatted_tools.append(
                {
                    "tool_key": f"{pack_meta.get('code') or capability_code}:{tool_id}",
                    "capability_code": pack_meta.get("code") or capability_code,
                    "id": tool_id,
                    "group": group,
                    "label": label.strip(),
                    "icon": icon.strip(),
                    "order": order,
                    "panel_component_code": panel_component_code,
                    "panel_component": _format_ui_component_for_response(
                        capability_code,
                        panel_component,
                    ),
                }
            )

        return sorted(formatted_tools, key=lambda item: (item["order"], item["tool_key"]))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get workspace tools for capability %s: %s",
            capability_code,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500, detail=f"Failed to get workspace tools: {str(e)}"
        )
