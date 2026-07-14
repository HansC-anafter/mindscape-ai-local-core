import json
import logging
import mimetypes
import os
import time
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, JSONResponse

from .cache_state import (
    clear_installed_capability_route_cache,
    get_cached_capability_route_payload,
    get_cached_runtime_ui_index,
    set_cached_capability_route_payload,
    set_cached_runtime_ui_index,
)
from .manifest_scan import (
    _format_installed_capability,
    _get_installed_pack_ids,
    _get_pack_meta_by_code,
    _scan_pack_yaml_files,
)
from .installed_route_workspace_tools import build_capability_workspace_tools
from .mobile_workbench_gateway_support import (
    build_mobile_workbench_gateway_support_payload,
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
                formatted = _format_installed_capability(pack_meta)
                capability_code = str(formatted.get("code") or pack_id).strip().lower()
                formatted["mobile_workbench_gateway_support"] = (
                    build_mobile_workbench_gateway_support_payload(
                        capability_code,
                        pack_meta,
                    )
                )
                installed_capabilities.append(formatted)

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
        cached_payload = get_cached_capability_route_payload(
            "installed-capability",
            capability_code,
        )
        if cached_payload is not None:
            return JSONResponse(content=cached_payload)

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

        payload = _format_installed_capability(pack_meta)
        set_cached_capability_route_payload(
            "installed-capability",
            capability_code,
            payload,
        )
        return JSONResponse(content=payload)
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
        cached_payload = get_cached_capability_route_payload(
            "ui-components",
            capability_code,
        )
        if cached_payload is not None:
            return cached_payload

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

        set_cached_capability_route_payload(
            "ui-components",
            capability_code,
            formatted_components,
        )
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
    payload = {
        "code": component.get("code"),
        "path": component_path,
        "description": component.get("description", ""),
        "export": component.get("export", "default"),
        "artifact_types": component.get("artifact_types", []),
        "playbook_codes": component.get("playbook_codes", []),
        "import_path": import_path,
        "layout_hint": component.get("layout_hint", "default"),
    }
    runtime_component = _get_runtime_ui_component(capability_code, component.get("code"))
    if runtime_component:
        payload.update(
            {
                "asset_url": runtime_component.get("asset_url"),
                "integrity": runtime_component.get("integrity"),
                "bytes": runtime_component.get("bytes"),
                "runtime": runtime_component.get("runtime"),
                "asset_path": runtime_component.get("asset_path"),
            }
        )
        if runtime_component.get("export"):
            payload["export"] = runtime_component["export"]
    return payload


def _runtime_ui_assets_root() -> Path:
    configured = os.getenv("MINDSCAPE_CAPABILITY_UI_ASSETS_DIR")
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[5] / "data" / "capability-ui"


def _load_runtime_ui_index(
    capability_code: str,
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    try:
        cached_payload = get_cached_runtime_ui_index(capability_code)
        if cached_payload is not None:
            return cached_payload

        pack_meta = _get_pack_meta_by_code(capability_code)
        manifest_file = pack_meta.get("_file_path") if pack_meta else None
        if not manifest_file:
            return {}
        sidecar_path = Path(manifest_file).parent / "ui_runtime_assets.json"
        if not sidecar_path.exists():
            return {}
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("runtime UI index must be an object")
        components = payload.get("components", [])
        if not isinstance(components, list) or any(
            not isinstance(component, dict) for component in components
        ):
            raise ValueError("runtime UI index components must be a list of objects")
        set_cached_runtime_ui_index(capability_code, payload)
        return payload
    except Exception as exc:
        logger.warning(
            "Failed to load runtime UI index for %s: %s",
            capability_code,
            exc,
        )
        if strict:
            raise RuntimeError(
                f"runtime UI index unavailable for {capability_code}"
            ) from exc
        return {}


def _get_runtime_ui_component(
    capability_code: str,
    component_code: Any,
    *,
    strict: bool = False,
) -> Dict[str, Any]:
    if not component_code:
        return {}
    runtime_index = _load_runtime_ui_index(capability_code, strict=strict)
    components = runtime_index.get("components", [])
    if not isinstance(components, list):
        return {}
    for component in components:
        if not isinstance(component, dict):
            continue
        if component.get("code") == component_code:
            return component
    return {}


@router.get("/installed-capabilities/{capability_code}/ui-assets/{asset_path:path}")
def get_capability_ui_asset(capability_code: str, asset_path: str):
    installed_ids = _get_installed_pack_ids()
    pack_meta = _get_pack_meta_by_code(capability_code)
    if not pack_meta or pack_meta.get("id") not in installed_ids:
        raise HTTPException(status_code=404, detail="Capability is not installed")

    safe_parts = [part for part in asset_path.split("/") if part not in {"", ".", ".."}]
    if "/".join(safe_parts) != asset_path:
        raise HTTPException(status_code=400, detail="Invalid UI asset path")

    asset_file = (_runtime_ui_assets_root() / capability_code / asset_path).resolve()
    try:
        asset_file.relative_to((_runtime_ui_assets_root() / capability_code).resolve())
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UI asset path")
    if not asset_file.exists() or not asset_file.is_file():
        raise HTTPException(status_code=404, detail="UI asset not found")

    media_type = mimetypes.guess_type(str(asset_file))[0] or "application/javascript"
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable",
        "X-Content-Type-Options": "nosniff",
    }
    return FileResponse(path=asset_file, media_type=media_type, headers=headers)


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

        return build_capability_workspace_tools(
            capability_code=capability_code,
            pack_meta=pack_meta,
            format_ui_component=_format_ui_component_for_response,
        )
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


@router.get(
    "/installed-capabilities/{capability_code}/mobile-workbench-gateway-support",
    response_model=Dict[str, Any],
)
def get_capability_mobile_workbench_gateway_support(capability_code: str):
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

        return build_mobile_workbench_gateway_support_payload(
            capability_code,
            pack_meta,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Failed to get mobile workbench gateway support for capability %s: %s",
            capability_code,
            e,
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get mobile workbench gateway support: {str(e)}",
        )
