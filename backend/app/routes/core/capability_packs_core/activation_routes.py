import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException

from backend.app.services.pack_activation_service import PackActivationService
from backend.app.services.stores.installed_packs_store import InstalledPacksStore

from .manifest_scan import (
    _get_enabled_pack_ids,
    _get_installed_pack_ids,
    _normalize_enabled_by_default,
    _scan_pack_yaml_files,
    _utc_now,
)
from .schemas import PackActivationStateResponse, PackResponse

logger = logging.getLogger(__name__)
router = APIRouter()
installed_packs_store = InstalledPacksStore()
pack_activation_service = PackActivationService()


@router.get("/", response_model=List[PackResponse])
def list_packs():
    """
    List all available capability packs

    Scans /packs/*.yaml files and returns pack information with installation/enablement status.
    """
    try:
        # Scan pack YAML files
        pack_metas = _scan_pack_yaml_files()

        installed_metadata = {}
        for row in installed_packs_store.list_installed_metadata():
            metadata = row.get("metadata") or {}
            installed_metadata[row["pack_id"]] = {
                "installed_at": row.get("installed_at"),
                "enabled": bool(row.get("enabled")),
                "version": metadata.get("version", "1.0.0"),
                "metadata": metadata,
            }
        installed_ids = set(installed_metadata.keys())
        enabled_ids = {
            pack_id
            for pack_id, metadata in installed_metadata.items()
            if metadata.get("enabled")
        }
        activation_states_by_pack_id = pack_activation_service.list_states_by_pack_id()

        packs = []
        for pack_meta in pack_metas:
            pack_id = pack_meta.get("id")
            if not pack_id:
                logger.warning(
                    f"Pack metadata missing 'id' field: {pack_meta.get('_file_path', 'unknown')}"
                )
                continue

            installed_info = installed_metadata.get(pack_id, {})
            installed_metadata_payload = installed_info.get("metadata") or {}
            validation_state = installed_metadata_payload.get("validation")
            activation_state = activation_states_by_pack_id.get(pack_id)

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
                    activation=(
                        PackActivationStateResponse(**activation_state)
                        if activation_state
                        else None
                    ),
                    validation=validation_state if isinstance(validation_state, dict) else None,
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
