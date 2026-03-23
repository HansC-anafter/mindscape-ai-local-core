"""
Capability Packs API

Registry and management of capability packs.
Provides endpoints for listing, enabling, and disabling packs.

Install endpoints have been extracted to ``capability_install.py``.
"""

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import JSONResponse
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import logging
import os
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml

from app.services.pack_activation_service import PackActivationService
from app.services.stores.installed_packs_store import InstalledPacksStore
from app.services.runtime_pack_hygiene import is_ignored_runtime_pack_dir

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/capability-packs", tags=["Capability Packs"])

installed_packs_store = InstalledPacksStore()
pack_activation_service = PackActivationService()


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


_pack_yaml_cache = None
_pack_yaml_cache_time = 0

_PACK_SOURCE_PRIORITY = {
    "legacy_pack_yaml": 1,
    "capability_manifest": 2,
    "feature_manifest": 3,
}

def _normalize_enabled_by_default(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _merge_unique_items(left: Any, right: Any) -> List[Any]:
    merged: List[Any] = []
    seen = set()
    for group in (left or [], right or []):
        if not isinstance(group, list):
            continue
        for item in group:
            marker = json.dumps(item, sort_keys=True, ensure_ascii=False, default=str)
            if marker in seen:
                continue
            seen.add(marker)
            merged.append(item)
    return merged


def _merge_pack_meta(existing: Dict[str, Any], candidate: Dict[str, Any]) -> Dict[str, Any]:
    existing_priority = _PACK_SOURCE_PRIORITY.get(
        existing.get("_source_kind", "legacy_pack_yaml"), 0
    )
    candidate_priority = _PACK_SOURCE_PRIORITY.get(
        candidate.get("_source_kind", "legacy_pack_yaml"), 0
    )

    primary = candidate if candidate_priority >= existing_priority else existing
    secondary = existing if primary is candidate else candidate

    merged = dict(primary)
    merged["routes"] = _merge_unique_items(
        secondary.get("routes"), primary.get("routes")
    )
    merged["playbooks"] = _merge_unique_items(
        secondary.get("playbooks"), primary.get("playbooks")
    )
    merged["tools"] = _merge_unique_items(
        secondary.get("tools"), primary.get("tools")
    )
    merged["ui_components"] = _merge_unique_items(
        secondary.get("ui_components"), primary.get("ui_components")
    )

    for key in ("description", "name", "display_name", "version", "enabled_by_default"):
        if merged.get(key) in (None, "", []):
            merged[key] = secondary.get(key)
    if not merged.get("_file_path"):
        merged["_file_path"] = secondary.get("_file_path")
    merged["enabled_by_default"] = _normalize_enabled_by_default(
        merged.get("enabled_by_default")
    )
    return merged


def _map_runtime_manifest(
    meta: Dict[str, Any],
    *,
    default_id: str,
    manifest_path: Path,
    source_kind: str,
) -> Dict[str, Any]:
    code = meta.get("code") or meta.get("id") or default_id
    name = meta.get("display_name") or meta.get("name") or code
    description = meta.get("description", "")

    playbooks = []
    for pb in meta.get("playbooks", []):
        if isinstance(pb, dict) and pb.get("code"):
            playbooks.append(pb["code"])
        elif isinstance(pb, str):
            playbooks.append(pb)

    mapped = {
        "id": code,
        "code": code,
        "name": name,
        "description": description,
        "version": meta.get("version", "1.0.0"),
        "enabled_by_default": _normalize_enabled_by_default(
            meta.get("enabled_by_default")
        ),
        "playbooks": playbooks,
        "ui_components": meta.get("ui_components", []),
        "_file_path": str(manifest_path),
        "_source_kind": source_kind,
    }
    for key, value in meta.items():
        if key not in mapped and key != "_file_path":
            mapped[key] = value
    return mapped

def _scan_pack_yaml_files(base_dir: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Scan all installed capabilities and return their manifest data.
    Results are cached for 60 seconds to avoid filesystem latency.
    """
    global _pack_yaml_cache, _pack_yaml_cache_time
    import time
    if (
        base_dir is None
        and _pack_yaml_cache is not None
        and (time.time() - _pack_yaml_cache_time < 60)
    ):
        return _pack_yaml_cache

    packs_by_id: Dict[str, Dict[str, Any]] = {}

    # Get packs directory
    # In Docker: /app/backend/app/routes/core/capability_packs.py -> /app/backend/packs
    # In local: backend/app/routes/core/capability_packs.py -> backend/packs
    base_dir = base_dir or Path(__file__).parent.parent.parent.parent
    packs_dir = base_dir / "packs"
    legacy_packs_dir: Optional[Path] = None

    # If packs directory doesn't exist at calculated path, try alternative locations
    if packs_dir.exists():
        legacy_packs_dir = packs_dir
    else:
        # Try /app/backend/packs (Docker)
        alt_path = Path("/app/backend/packs")
        if alt_path.exists():
            legacy_packs_dir = alt_path
        else:
            # Try backend/packs (local dev)
            alt_path = base_dir / "backend" / "packs"
            if alt_path.exists():
                legacy_packs_dir = alt_path
            else:
                logger.warning(
                    f"Packs directory not found. Tried: {base_dir / 'packs'}, {Path('/app/backend/packs')}, {base_dir / 'backend' / 'packs'}"
                )

    # Scan for .yaml files
    if legacy_packs_dir is not None:
        for pack_file in legacy_packs_dir.glob("*.yaml"):
            meta = _load_manifest_file(pack_file)
            if meta:
                meta["_source_kind"] = "legacy_pack_yaml"
                pack_id = meta.get("id") or meta.get("code")
                if not pack_id:
                    continue
                existing = packs_by_id.get(pack_id)
                packs_by_id[pack_id] = (
                    _merge_pack_meta(existing, meta) if existing else meta
                )

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
            if not cap_dir.is_dir() or is_ignored_runtime_pack_dir(cap_dir.name):
                continue
            manifest_path = cap_dir / "manifest.yaml"
            if manifest_path.exists():
                meta = _load_manifest_file(manifest_path)
                if not meta:
                    continue
                meta_mapped = _map_runtime_manifest(
                    meta,
                    default_id=cap_dir.name,
                    manifest_path=manifest_path,
                    source_kind="capability_manifest",
                )
                pack_id = meta_mapped["id"]
                existing = packs_by_id.get(pack_id)
                packs_by_id[pack_id] = (
                    _merge_pack_meta(existing, meta_mapped)
                    if existing
                    else meta_mapped
                )

    features_dir = base_dir / "features"
    if not features_dir.exists():
        alt_paths = [
            Path("/app/backend/features"),
            base_dir / "backend" / "features",
        ]
        for alt_path in alt_paths:
            if alt_path.exists():
                features_dir = alt_path
                break

    if features_dir.exists():
        for feature_dir in features_dir.iterdir():
            if not feature_dir.is_dir() or is_ignored_runtime_pack_dir(feature_dir.name):
                continue
            manifest_path = feature_dir / "manifest.yaml"
            if not manifest_path.exists():
                continue
            meta = _load_manifest_file(manifest_path)
            if not meta:
                continue
            meta_mapped = _map_runtime_manifest(
                meta,
                default_id=feature_dir.name,
                manifest_path=manifest_path,
                source_kind="feature_manifest",
            )
            pack_id = meta_mapped["id"]
            existing = packs_by_id.get(pack_id)
            packs_by_id[pack_id] = (
                _merge_pack_meta(existing, meta_mapped) if existing else meta_mapped
            )

    packs = list(packs_by_id.values())
    if base_dir == Path(__file__).parent.parent.parent.parent:
        _pack_yaml_cache = packs
        _pack_yaml_cache_time = time.time()
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


class PackActivationStateResponse(BaseModel):
    pack_id: str
    pack_family: str
    enabled: bool
    install_state: str
    migration_state: str
    activation_state: str
    activation_mode: str
    embedding_state: str = "unknown"
    embedding_error: Optional[str] = None
    embeddings_updated_at: Optional[str] = None
    manifest_hash: Optional[str] = None
    registered_prefixes: List[str] = Field(default_factory=list)
    last_error: Optional[str] = None
    activated_at: Optional[str] = None
    updated_at: Optional[str] = None


@router.get("/", response_model=List[PackResponse])
def list_packs():
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
                    enabled_by_default=_normalize_enabled_by_default(
                        pack_meta.get("enabled_by_default")
                    ),
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
    import anyio
    try:
        def _do_enable():
            # Check if pack exists in YAML files
            pack_metas = _scan_pack_yaml_files()
            pack_meta = next((p for p in pack_metas if p.get("id") == pack_id), None)
            return pack_meta

        pack_meta = await anyio.to_thread.run_sync(_do_enable)

        if not pack_meta:
            raise HTTPException(
                status_code=404, detail=f"Capability pack '{pack_id}' not found"
            )

        def _do_db_enable():
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

        await anyio.to_thread.run_sync(_do_db_enable)
        await anyio.to_thread.run_sync(
            lambda: pack_activation_service.record_enabled(
                pack_id=pack_id,
                manifest=pack_meta,
                manifest_path=Path(pack_meta["_file_path"])
                if pack_meta.get("_file_path")
                else None,
            )
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
                    try:
                        pack_activation_service.record_embedding_succeeded(
                            pack_id=pack_id,
                            manifest=pack_meta,
                            manifest_path=Path(pack_meta["_file_path"])
                            if pack_meta.get("_file_path")
                            else None,
                        )
                    except Exception as _state_exc:
                        logger.warning(
                            "Failed to persist embedding success state for %s: %s",
                            pack_id,
                            _state_exc,
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
                    try:
                        pack_activation_service.record_embedding_failed(
                            pack_id=pack_id,
                            manifest=pack_meta,
                            error=str(_exc),
                            manifest_path=Path(pack_meta["_file_path"])
                            if pack_meta.get("_file_path")
                            else None,
                        )
                    except Exception as _state_exc:
                        logger.warning(
                            "Failed to persist embedding failure state for %s: %s",
                            pack_id,
                            _state_exc,
                        )

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
    import anyio
    try:
        updated = await anyio.to_thread.run_sync(
            installed_packs_store.set_enabled, pack_id, False
        )
        if not updated:
            raise HTTPException(
                status_code=404, detail=f"Pack '{pack_id}' is not installed"
            )
        await anyio.to_thread.run_sync(pack_activation_service.record_disabled, pack_id)

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
def list_installed_packs():
    """List all installed pack IDs"""
    return installed_packs_store.list_installed_pack_ids()


@router.get("/{pack_id}/activation", response_model=PackActivationStateResponse)
def get_pack_activation_state(pack_id: str):
    """Return persisted activation/install state for a pack."""
    state = pack_activation_service.get_state(pack_id)
    if state is None:
        raise HTTPException(
            status_code=404,
            detail=f"Activation state for pack '{pack_id}' not found",
        )
    return PackActivationStateResponse(**state)


@router.get("/enabled", response_model=List[str])
def list_enabled_packs():
    """List all enabled pack IDs"""
    return list(_get_enabled_pack_ids())


@router.get("/installed-capabilities")
def list_installed_capabilities():
    """
    List all installed capability packs with detailed information

    Returns list of installed packs with their metadata.
    This endpoint is used by the frontend to display installed capabilities.
    """
    import time
    t0 = time.time()
    print(f"[{t0:.3f}] list_installed_capabilities - Start")
    try:
        # Get all packs
        pack_metas = _scan_pack_yaml_files()
        t1 = time.time()
        print(f"[{t1:.3f}] list_installed_capabilities - Scanned YAML (in {t1-t0:.3f}s)")

        # Get installed pack IDs
        installed_ids = _get_installed_pack_ids()
        t2 = time.time()
        print(f"[{t2:.3f}] list_installed_capabilities - Got installed IDs (in {t2-t1:.3f}s)")

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

        t3 = time.time()
        print(f"[{t3:.3f}] list_installed_capabilities - Mapped response (in {t3-t2:.3f}s)")
        print(f"[{t3:.3f}] list_installed_capabilities - Returning JSON (total {t3-t0:.3f}s)")
        return JSONResponse(content=installed_capabilities)
    except Exception as e:
        logger.error(f"Failed to list installed capabilities: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Failed to list installed capabilities: {str(e)}"
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
