"""
Capability Packs API

Registry and management of capability packs.
Provides endpoints for listing, enabling, and disabling packs.

Install endpoints have been extracted to ``capability_install.py``.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.services.stores.installed_packs_store import InstalledPacksStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/capability-packs", tags=["Capability Packs"])

installed_packs_store = InstalledPacksStore()


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def _load_manifest_file(manifest_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            pack_meta = yaml.safe_load(f)
            if pack_meta and isinstance(pack_meta, dict):
                pack_meta["_file_path"] = str(manifest_path)
                # Resolve external schema_path references in tool definitions
                from backend.app.services.manifest_utils import (
                    resolve_tool_schema_paths,
                )

                resolve_tool_schema_paths(pack_meta, manifest_path.parent)
                return pack_meta
    except Exception as e:
        logger.warning(f"Failed to load pack file {manifest_path}: {e}")
    return None


def _scan_pack_yaml_files() -> List[Dict[str, Any]]:
    """
    Scan for pack YAML files in /packs directory and cloud capability manifests

    Returns:
        List of pack metadata dictionaries
    """
    packs = []

    # Get packs directory
    # In Docker: /app/backend/app/routes/core/capability_packs.py -> /app/backend/packs
    # In local: backend/app/routes/core/capability_packs.py -> backend/packs
    base_dir = Path(__file__).parent.parent.parent.parent
    packs_dir = base_dir / "packs"

    # If packs directory doesn't exist at calculated path, try alternative locations
    if not packs_dir.exists():
        # Try /app/backend/packs (Docker)
        alt_path = Path("/app/backend/packs")
        if alt_path.exists():
            packs_dir = alt_path
        else:
            # Try backend/packs (local dev)
            alt_path = base_dir / "backend" / "packs"
            if alt_path.exists():
                packs_dir = alt_path
            else:
                logger.warning(
                    f"Packs directory not found. Tried: {base_dir / 'packs'}, {Path('/app/backend/packs')}, {base_dir / 'backend' / 'packs'}"
                )
                return packs

    # Scan for .yaml files
    for pack_file in packs_dir.glob("*.yaml"):
        meta = _load_manifest_file(pack_file)
        if meta:
            packs.append(meta)

    # Scan installed capabilities from backend/app/capabilities/
    capabilities_dir = base_dir / "app" / "capabilities"
    if not capabilities_dir.exists():
        alt_paths = [
            Path("/app/backend/app/capabilities"),  # Docker
            base_dir / "backend" / "app" / "capabilities",  # Local dev
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                capabilities_dir = alt_path
                break

    if capabilities_dir.exists():
        for cap_dir in capabilities_dir.iterdir():
            if not cap_dir.is_dir():
                continue
            manifest_path = cap_dir / "manifest.yaml"
            if manifest_path.exists():
                meta = _load_manifest_file(manifest_path)
                if not meta:
                    continue
                # Map manifest fields to pack meta fields expected by API
                code = meta.get("code") or cap_dir.name
                name = meta.get("display_name") or meta.get("name") or code
                description = meta.get("description", "")
                # Attach playbook codes for visibility (if present)
                playbooks = []
                for pb in meta.get("playbooks", []):
                    if isinstance(pb, dict) and pb.get("code"):
                        playbooks.append(pb["code"])
                    elif isinstance(pb, str):
                        playbooks.append(pb)
                meta_mapped = {
                    "id": code,  # Use code as id
                    "name": name or cap_dir.name,
                    "description": description,
                    "version": meta.get("version", "1.0.0"),
                    "playbooks": playbooks,
                    "ui_components": meta.get(
                        "ui_components", []
                    ),  # Include UI components
                    "_file_path": str(manifest_path),
                }
                # Merge other fields from original meta
                for key, value in meta.items():
                    if key not in meta_mapped and key != "_file_path":
                        meta_mapped[key] = value
                packs.append(meta_mapped)

    return packs


def _get_installed_pack_ids() -> set:
    """Get set of installed pack IDs from database"""
    return set(installed_packs_store.list_installed_pack_ids())


def _get_enabled_pack_ids() -> set:
    """Get set of enabled pack IDs from database"""
    return set(installed_packs_store.list_enabled_pack_ids())


class PackResponse(BaseModel):
    """Response model for pack information"""

    id: str
    name: str
    description: str
    enabled_by_default: bool = False
    enabled: bool = False
    installed: bool = False
    routes: List[str] = []
    playbooks: List[str] = []
    tools: List[str] = []
    version: Optional[str] = None
    installed_at: Optional[str] = None


@router.get("/", response_model=List[PackResponse])
async def list_packs():
    """
    List all available capability packs

    Scans /packs/*.yaml files and returns pack information with installation/enablement status.
    """
    try:
        # Scan pack YAML files
        pack_metas = _scan_pack_yaml_files()

        # Get installed and enabled pack IDs
        installed_ids = _get_installed_pack_ids()
        enabled_ids = _get_enabled_pack_ids()

        installed_metadata = {}
        for row in installed_packs_store.list_installed_metadata():
            metadata = row.get("metadata") or {}
            installed_metadata[row["pack_id"]] = {
                "installed_at": row.get("installed_at"),
                "version": metadata.get("version", "1.0.0"),
            }

        packs = []
        for pack_meta in pack_metas:
            pack_id = pack_meta.get("id")
            if not pack_id:
                logger.warning(
                    f"Pack metadata missing 'id' field: {pack_meta.get('_file_path', 'unknown')}"
                )
                continue

            installed_info = installed_metadata.get(pack_id, {})

            # Handle tools field: if it's a list of dicts, extract tool names
            tools_raw = pack_meta.get("tools", [])
            tools_list = []
            if isinstance(tools_raw, list):
                for tool in tools_raw:
                    if isinstance(tool, str):
                        tools_list.append(tool)
                    elif isinstance(tool, dict):
                        # Extract tool name from dict
                        tool_name = (
                            tool.get("name") or tool.get("id") or tool.get("tool")
                        )
                        if tool_name:
                            tools_list.append(tool_name)

            playbooks_raw = pack_meta.get("playbooks", [])
            playbooks_list = []
            if isinstance(playbooks_raw, list):
                for pb in playbooks_raw:
                    if isinstance(pb, str):
                        playbooks_list.append(pb)
                    elif isinstance(pb, dict):
                        pb_code = pb.get("code") or pb.get("id") or pb.get("playbook")
                        if pb_code:
                            playbooks_list.append(pb_code)

            packs.append(
                PackResponse(
                    id=pack_id,
                    name=pack_meta.get("name", pack_id),
                    description=pack_meta.get("description", ""),
                    enabled_by_default=pack_meta.get("enabled_by_default", False),
                    enabled=pack_id in enabled_ids,
                    installed=pack_id in installed_ids,
                    routes=pack_meta.get("routes", []),
                    playbooks=playbooks_list,
                    tools=tools_list,
                    version=installed_info.get("version")
                    or pack_meta.get("version", "1.0.0"),
                    installed_at=installed_info.get("installed_at"),
                )
            )

        return packs

    except Exception as e:
        logger.error(f"Failed to list packs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list packs: {str(e)}")


@router.post("/{pack_id}/enable", response_model=Dict[str, Any])
async def enable_pack(pack_id: str):
    """
    Enable a capability pack

    Enables a pack that has been installed. If the pack is not installed,
    it will be installed first (if enabled_by_default is True).
    """
    try:
        # Check if pack exists in YAML files
        pack_metas = _scan_pack_yaml_files()
        pack_meta = next((p for p in pack_metas if p.get("id") == pack_id), None)

        if not pack_meta:
            raise HTTPException(
                status_code=404, detail=f"Capability pack '{pack_id}' not found"
            )

        existing = installed_packs_store.get_pack(pack_id)
        if existing:
            installed_packs_store.set_enabled(pack_id, True)
        else:
            installed_packs_store.upsert_pack(
                pack_id=pack_id,
                installed_at=_utc_now(),
                enabled=True,
                metadata=pack_meta,
            )

        # Rebuild tool embeddings for re-enabled pack (background, non-fatal)
        import asyncio as _asyncio

        try:
            from backend.app.services.tool_embedding_service import (
                ToolEmbeddingService as _TES,
            )

            async def _bg_reindex():
                try:
                    n = await _TES().ensure_indexed()
                    if n <= 0:
                        n = await _TES().index_all_tools()
                    logger.info(
                        "Tool RAG re-indexed after enable %s: %d tools", pack_id, n
                    )
                    # Invalidate process-level cache so next turn gets fresh results
                    try:
                        from backend.app.services.tool_rag import (
                            invalidate_tool_rag_cache,
                        )

                        invalidate_tool_rag_cache()
                    except Exception:
                        pass
                except Exception as _exc:
                    logger.warning("Tool RAG re-indexing failed (non-fatal): %s", _exc)

            _asyncio.create_task(_bg_reindex())
        except Exception as exc:
            logger.warning("Tool RAG background task setup failed: %s", exc)

        return {
            "success": True,
            "pack_id": pack_id,
            "message": f"Capability pack '{pack_id}' enabled successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to enable pack: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to enable pack: {str(e)}")


@router.post("/{pack_id}/disable", response_model=Dict[str, Any])
async def disable_pack(pack_id: str):
    """
    Disable a capability pack

    Disables a pack but does not uninstall it. The pack can be re-enabled later.
    """
    try:
        updated = installed_packs_store.set_enabled(pack_id, False)
        if not updated:
            raise HTTPException(
                status_code=404, detail=f"Pack '{pack_id}' is not installed"
            )

        # Remove tool embeddings for disabled pack (background, non-fatal)
        import asyncio as _asyncio

        try:
            from backend.app.services.tool_embedding_service import (
                ToolEmbeddingService as _TES,
            )

            async def _bg_remove():
                try:
                    n = await _TES().remove_tools_by_capability(pack_id)
                    logger.info(
                        "Tool RAG: removed %d embeddings for disabled pack %s",
                        n,
                        pack_id,
                    )
                    # Invalidate process-level cache so next turn gets fresh results
                    try:
                        from backend.app.services.tool_rag import (
                            invalidate_tool_rag_cache,
                        )

                        invalidate_tool_rag_cache()
                    except Exception:
                        pass
                except Exception as _exc:
                    logger.warning("Tool RAG cleanup failed (non-fatal): %s", _exc)

            _asyncio.create_task(_bg_remove())
        except Exception as exc:
            logger.warning("Tool RAG background task setup failed: %s", exc)

        return {
            "success": True,
            "pack_id": pack_id,
            "message": f"Capability pack '{pack_id}' disabled successfully",
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable pack: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to disable pack: {str(e)}")


@router.get("/installed", response_model=List[str])
async def list_installed_packs():
    """List all installed pack IDs"""
    return installed_packs_store.list_installed_pack_ids()


@router.get("/enabled", response_model=List[str])
async def list_enabled_packs():
    """List all enabled pack IDs"""
    return list(_get_enabled_pack_ids())


@router.get("/installed-capabilities", response_model=List[Dict[str, Any]])
async def list_installed_capabilities():
    """
    List all installed capability packs with detailed information

    Returns list of installed packs with their metadata.
    This endpoint is used by the frontend to display installed capabilities.
    """
    try:
        # Get all packs
        pack_metas = _scan_pack_yaml_files()

        # Get installed pack IDs
        installed_ids = _get_installed_pack_ids()

        # Filter to only installed packs and format response
        installed_capabilities = []
        for pack_meta in pack_metas:
            pack_id = pack_meta.get("id")
            if pack_id and pack_id in installed_ids:
                installed_capabilities.append(
                    {
                        "id": pack_id,
                        "code": pack_meta.get(
                            "code", pack_id
                        ),  # Use code from meta if available
                        "display_name": pack_meta.get("name", pack_id),
                        "version": pack_meta.get("version", "1.0.0"),
                        "description": pack_meta.get("description", ""),
                        "scope": pack_meta.get("scope", "global"),
                        "ui_components": pack_meta.get(
                            "ui_components", []
                        ),  # Include UI components info
                    }
                )

        return installed_capabilities
    except Exception as e:
        logger.error(f"Failed to list installed capabilities: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list installed capabilities: {str(e)}"
        )


@router.get(
    "/installed-capabilities/{capability_code}/ui-components",
    response_model=List[Dict[str, Any]],
)
async def get_capability_ui_components(capability_code: str):
    """
    Get UI components information for an installed capability

    Returns UI components metadata from the capability's manifest.
    Frontend uses this to dynamically load UI components.

    Boundary: This API only reads manifest metadata, does not serve component code.
    Component code must be installed via RuntimeAssetsInstaller, not hardcoded.
    """
    try:
        # Get all packs
        pack_metas = _scan_pack_yaml_files()

        pack_meta = next(
            (
                p
                for p in pack_metas
                if p.get("id") == capability_code or p.get("code") == capability_code
            ),
            None,
        )

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

        # Format response with component metadata
        formatted_components = []
        for component in ui_components:
            # Component path from manifest (e.g., "ui/pages/ChapterStudioPage.tsx" or "ui/components/WorkbenchLayout.tsx")
            component_path = component.get("path", "")
            component_filename = Path(component_path).name
            component_name = component_filename.replace(".tsx", "").replace(".ts", "")

            # Extract subdirectory from path (e.g., "pages" from "ui/pages/ChapterStudioPage.tsx")
            # Path structure: ui/{subdirectory}/{filename}
            path_parts = component_path.split("/")
            subdirectory = "components"  # default
            if len(path_parts) >= 3 and path_parts[0] == "ui":
                # Extract subdirectory (e.g., "pages", "components")
                subdirectory = path_parts[1]

            # Build import path based on actual file structure
            import_path = (
                f"@/app/capabilities/{capability_code}/{subdirectory}/{component_name}"
            )

            formatted_components.append(
                {
                    "code": component.get("code"),
                    "path": component_path,
                    "description": component.get("description", ""),
                    "export": component.get("export", "default"),
                    "artifact_types": component.get("artifact_types", []),
                    "playbook_codes": component.get("playbook_codes", []),
                    "import_path": import_path,
                }
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
