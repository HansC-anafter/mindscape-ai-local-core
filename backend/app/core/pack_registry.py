"""
Pack Registry Loader

Dynamically loads and registers feature routes from pack YAML files.
Scans /packs/*.yaml and registers enabled packs' routes.
"""

import importlib
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, APIRouter
import yaml

logger = logging.getLogger(__name__)

from app.services.stores.installed_packs_store import InstalledPacksStore


def load_pack_yaml(pack_path: Path) -> Dict[str, Any]:
    """
    Load pack metadata from YAML file

    Args:
        pack_path: Path to pack YAML file

    Returns:
        Pack metadata dictionary
    """
    try:
        with open(pack_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to load pack YAML {pack_path}: {e}")
        raise


def load_router_from_string(import_string: str) -> APIRouter:
    """
    Load router from import string (e.g., 'backend.features.habits.routes:router')

    Args:
        import_string: Import string in format 'module.path:attribute'

    Returns:
        APIRouter instance

    Raises:
        ImportError: If module or attribute cannot be imported
        AttributeError: If attribute does not exist in module
    """
    try:
        module_path, attr_name = import_string.split(':')

        # Ensure backend module is in path for absolute imports
        if module_path.startswith('backend.'):
            import sys
            current_file = Path(__file__).resolve()
            backend_dir = current_file.parent.parent.parent
            project_root = backend_dir.parent
            if str(project_root) not in sys.path:
                sys.path.insert(0, str(project_root))

        module = importlib.import_module(module_path)
        router = getattr(module, attr_name)

        if not isinstance(router, APIRouter):
            raise ValueError(f"Attribute '{attr_name}' in '{module_path}' is not an APIRouter")

        return router
    except ValueError as e:
        logger.error(f"Invalid import string format '{import_string}': {e}")
        raise
    except ImportError as e:
        logger.error(f"Failed to import module from '{import_string}': {e}")
        raise
    except AttributeError as e:
        logger.error(f"Attribute '{attr_name}' not found in module '{module_path}': {e}")
        raise


def scan_packs_directory(packs_dir: Path) -> List[Dict[str, Any]]:
    """
    Scan packs directory for YAML files

    Args:
        packs_dir: Path to packs directory

    Returns:
        List of pack metadata dictionaries
    """
    packs = []

    if not packs_dir.exists():
        logger.warning(f"Packs directory not found: {packs_dir}")
        return packs

    for pack_file in packs_dir.glob("*.yaml"):
        try:
            pack_meta = load_pack_yaml(pack_file)
            if pack_meta and isinstance(pack_meta, dict):
                pack_meta['_file_path'] = str(pack_file)
                packs.append(pack_meta)
        except Exception as e:
            logger.warning(f"Failed to load pack file {pack_file}: {e}")

    return packs


def _auto_install_default_packs(pack_metas: List[Dict[str, Any]], default_enabled_packs: set, enabled_pack_ids: set) -> None:
    """
    Automatically install packs with enabled_by_default=True that are not yet installed

    This ensures that default-enabled packs are available in the database
    even if they haven't been manually installed through the UI.
    """
    try:
        store = InstalledPacksStore()
        packs_to_install = default_enabled_packs - enabled_pack_ids
        if not packs_to_install:
            return

        for pack_id in packs_to_install:
            pack_meta = next((p for p in pack_metas if p.get("id") == pack_id), None)
            if not pack_meta:
                continue
            metadata = {
                "name": pack_meta.get("name", pack_id),
                "description": pack_meta.get("description", ""),
                "enabled_by_default": True,
            }
            store.upsert_pack(
                pack_id=pack_id,
                installed_at=datetime.utcnow(),
                enabled=True,
                metadata=metadata,
            )
        logger.info(
            "Auto-installed %d default-enabled packs: %s",
            len(packs_to_install),
            packs_to_install,
        )
    except Exception as e:
        logger.warning(f"Failed to auto-install default packs: {e}")


def get_enabled_pack_ids() -> set:
    """
    Get set of enabled pack IDs from database

    Returns:
        Set of enabled pack IDs
    """
    try:
        store = InstalledPacksStore()
        return set(store.list_enabled_pack_ids())
    except Exception as e:
        logger.warning(f"Failed to get enabled pack IDs from database: {e}")
        return set()


def load_and_register_packs(app: FastAPI, packs_dir: Optional[Path] = None) -> None:
    """
    Scan packs directory and register enabled packs' routes

    Args:
        app: FastAPI application instance
        packs_dir: Optional path to packs directory. If not provided, uses default location.
    """
    if packs_dir is None:
        # Default to backend/packs
        # In Docker: /app/backend/app/core/pack_registry.py -> /app/backend/packs
        # In local: backend/app/core/pack_registry.py -> backend/packs
        base_dir = Path(__file__).parent.parent.parent
        packs_dir = base_dir / "packs"

        # If packs directory doesn't exist at calculated path, try alternative locations
        if not packs_dir.exists():
            # Try /app/backend/packs (Docker)
            alt_path = Path("/app/backend/packs")
            if alt_path.exists():
                packs_dir = alt_path
            else:
                # Try backend/packs (local dev)
                alt_path = Path("backend/packs")
                if alt_path.exists():
                    packs_dir = alt_path

    logger.info(f"Scanning packs directory: {packs_dir}")

    # Scan for pack YAML files
    pack_metas = scan_packs_directory(packs_dir)

    if not pack_metas:
        logger.warning(f"No pack YAML files found in {packs_dir}")
        return

    # Get enabled pack IDs from database
    enabled_pack_ids = get_enabled_pack_ids()

    # Also include packs with enabled_by_default=True
    default_enabled_packs = {
        pack['id'] for pack in pack_metas
        if pack.get('enabled_by_default', False)
    }

    # Auto-install default-enabled packs that are not yet installed
    _auto_install_default_packs(pack_metas, default_enabled_packs, enabled_pack_ids)

    # Combine enabled and default-enabled packs
    packs_to_load = enabled_pack_ids | default_enabled_packs

    logger.info(f"Found {len(pack_metas)} packs, {len(packs_to_load)} enabled")

    # Register routes for enabled packs
    registered_count = 0
    for pack in pack_metas:
        pack_id = pack.get('id')
        if not pack_id:
            logger.warning(f"Pack metadata missing 'id' field: {pack.get('_file_path', 'unknown')}")
            continue

        # Check if pack should be loaded
        if pack_id not in packs_to_load:
            logger.debug(f"Skipping disabled pack: {pack_id}")
            continue

        # Load and register routes
        routes = pack.get('routes', [])
        if not routes:
            logger.debug(f"Pack {pack_id} has no routes defined")
            continue

        for route_import in routes:
            try:
                router = load_router_from_string(route_import)
                # For workspace pack, routes already have prefix, don't add another
                # For other packs, add pack_id as prefix
                if pack_id == "workspace":
                    app.include_router(router, tags=[pack_id])
                else:
                    prefix = f"/api/v1/{pack_id}"
                    app.include_router(router, prefix=prefix, tags=[pack_id])
                registered_count += 1
                logger.info(f"Registered route from pack '{pack_id}': {route_import}")
            except Exception as e:
                # Log error but continue - loose coupling: missing features should not prevent app startup
                logger.warning(
                    f"Failed to register route '{route_import}' from pack '{pack_id}': {e}. "
                    f"Pack will be skipped but app will continue to start."
                )
                # Continue to next route instead of failing
                continue

    logger.info(f"Successfully registered {registered_count} routes from {len(packs_to_load)} enabled packs")
