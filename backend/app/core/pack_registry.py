"""
Pack Registry Loader

Dynamically loads and registers feature routes from pack YAML files.
Scans /packs/*.yaml and registers enabled packs' routes.
"""

import importlib
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, APIRouter
import yaml

logger = logging.getLogger(__name__)


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


def get_enabled_pack_ids() -> set:
    """
    Get set of enabled pack IDs from database

    Returns:
        Set of enabled pack IDs
    """
    try:
        import sqlite3
        from contextlib import contextmanager
        import os

        def get_db_path():
            base_dir = Path(__file__).parent.parent.parent
            data_dir = base_dir / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            return str(data_dir / "mindscape.db")

        @contextmanager
        def get_connection():
            conn = sqlite3.connect(get_db_path())
            conn.row_factory = sqlite3.Row
            try:
                yield conn
            finally:
                conn.close()

        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT pack_id FROM installed_packs WHERE enabled = 1')
            return {row['pack_id'] for row in cursor.fetchall()}
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
                prefix = f"/api/features/{pack_id}"
                app.include_router(router, prefix=prefix, tags=[pack_id])
                registered_count += 1
                logger.info(f"Registered route from pack '{pack_id}': {route_import} (prefix: {prefix})")
            except Exception as e:
                # Log error but continue - loose coupling: missing features should not prevent app startup
                logger.warning(
                    f"Failed to register route '{route_import}' from pack '{pack_id}': {e}. "
                    f"Pack will be skipped but app will continue to start."
                )
                # Continue to next route instead of failing
                continue

    logger.info(f"Successfully registered {registered_count} routes from {len(packs_to_load)} enabled packs")

