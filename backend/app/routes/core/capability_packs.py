"""
Capability Packs API

Handles installation and management of capability packs.
Provides registry API for listing, enabling, and disabling packs.

Packs are loaded from /packs/*.yaml files or plugin registry.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel
import json
import sqlite3
from contextlib import contextmanager
import os
from datetime import datetime
from pathlib import Path
import tempfile
import logging
import yaml

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/capability-packs", tags=["Capability Packs"])

# Database helper
def get_db_path():
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    data_dir = os.path.join(base_dir, "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "mindscape.db")

@contextmanager
def get_connection():
    conn = sqlite3.connect(get_db_path())
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()

def _init_installed_packs_table():
    """Initialize installed_packs table"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS installed_packs (
                pack_id TEXT PRIMARY KEY,
                installed_at TEXT NOT NULL,
                enabled BOOLEAN DEFAULT 1,
                metadata TEXT
            )
        ''')
        conn.commit()

# Initialize table on module load
_init_installed_packs_table()


def _scan_pack_yaml_files() -> List[Dict[str, Any]]:
    """
    Scan for pack YAML files in /packs directory

    Returns:
        List of pack metadata dictionaries
    """
    packs = []

    # Get packs directory
    base_dir = Path(__file__).parent.parent.parent.parent
    packs_dir = base_dir / "backend" / "packs"

    if not packs_dir.exists():
        logger.warning(f"Packs directory not found: {packs_dir}")
        return packs

    # Scan for .yaml files
    for pack_file in packs_dir.glob("*.yaml"):
        try:
            with open(pack_file, 'r', encoding='utf-8') as f:
                pack_meta = yaml.safe_load(f)
                if pack_meta and isinstance(pack_meta, dict):
                    pack_meta['_file_path'] = str(pack_file)
                    packs.append(pack_meta)
        except Exception as e:
            logger.warning(f"Failed to load pack file {pack_file}: {e}")

    return packs


def _get_installed_pack_ids() -> set:
    """Get set of installed pack IDs from database"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT pack_id FROM installed_packs WHERE enabled = 1')
        return {row['pack_id'] for row in cursor.fetchall()}


def _get_enabled_pack_ids() -> set:
    """Get set of enabled pack IDs from database"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT pack_id FROM installed_packs WHERE enabled = 1')
        return {row['pack_id'] for row in cursor.fetchall()}


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

        packs = []
        for pack_meta in pack_metas:
            pack_id = pack_meta.get('id')
            if not pack_id:
                logger.warning(f"Pack metadata missing 'id' field: {pack_meta.get('_file_path', 'unknown')}")
                continue

            packs.append(PackResponse(
                id=pack_id,
                name=pack_meta.get('name', pack_id),
                description=pack_meta.get('description', ''),
                enabled_by_default=pack_meta.get('enabled_by_default', False),
                enabled=pack_id in enabled_ids,
                installed=pack_id in installed_ids,
                routes=pack_meta.get('routes', []),
                playbooks=pack_meta.get('playbooks', []),
                tools=pack_meta.get('tools', [])
            ))

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
        pack_meta = next((p for p in pack_metas if p.get('id') == pack_id), None)

        if not pack_meta:
            raise HTTPException(status_code=404, detail=f"Capability pack '{pack_id}' not found")

        with get_connection() as conn:
            cursor = conn.cursor()

            # Check if already installed
            cursor.execute('SELECT pack_id, enabled FROM installed_packs WHERE pack_id = ?', (pack_id,))
            existing = cursor.fetchone()

            if existing:
                # Update enabled status
                cursor.execute('''
                    UPDATE installed_packs
                    SET enabled = 1
                    WHERE pack_id = ?
                ''', (pack_id,))
            else:
                # Install and enable
                cursor.execute('''
                    INSERT INTO installed_packs (pack_id, installed_at, enabled, metadata)
                    VALUES (?, ?, 1, ?)
                ''', (
                    pack_id,
                    datetime.utcnow().isoformat(),
                    json.dumps(pack_meta)
                ))

            conn.commit()

        return {
            "success": True,
            "pack_id": pack_id,
            "message": f"Capability pack '{pack_id}' enabled successfully"
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
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE installed_packs
                SET enabled = 0
                WHERE pack_id = ?
            ''', (pack_id,))
            conn.commit()

            if cursor.rowcount == 0:
                raise HTTPException(status_code=404, detail=f"Pack '{pack_id}' is not installed")

        return {
            "success": True,
            "pack_id": pack_id,
            "message": f"Capability pack '{pack_id}' disabled successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to disable pack: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to disable pack: {str(e)}")


@router.get("/installed", response_model=List[str])
async def list_installed_packs():
    """List all installed pack IDs"""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT pack_id FROM installed_packs')
        return [row['pack_id'] for row in cursor.fetchall()]


@router.get("/enabled", response_model=List[str])
async def list_enabled_packs():
    """List all enabled pack IDs"""
    return list(_get_enabled_pack_ids())


# ============================================
# .mindpack File Installation (Offline Capability Packs)
# ============================================

@router.post("/install-from-file", response_model=Dict[str, Any])
async def install_from_file(
    file: UploadFile = File(...),
    allow_overwrite: str = Form("false"),
    profile_id: str = Query("default-user", description="User profile ID for role mapping")
):
    """
    Install capability package from .mindpack file

    Supports offline installation of capability packages.
    Validates manifest, checks conflicts, and installs to capabilities directory.
    """
    if not file.filename.endswith('.mindpack'):
        raise HTTPException(
            status_code=400,
            detail="File must be a .mindpack file"
        )

    try:
        import sys
        from pathlib import Path

        # Get backend directory and add to sys.path
        current_file = Path(__file__).resolve()
        app_dir = current_file.parent.parent  # app/routes -> app
        backend_dir = app_dir.parent  # app -> backend

        backend_dir_str = str(backend_dir)
        if backend_dir_str not in sys.path:
            sys.path.insert(0, backend_dir_str)

        from app.services.capability_installer import CapabilityInstaller

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mindpack') as tmp_file:
            content = await file.read()
            tmp_file.write(content)
            tmp_path = Path(tmp_file.name)

        try:
            allow_overwrite_bool = allow_overwrite.lower() in ('true', '1', 'yes', 'on')
            installer = CapabilityInstaller()
            result = installer.install_from_file(tmp_path, allow_overwrite=allow_overwrite_bool)

            if not result.get('success'):
                error_msg = result.get('error', 'Installation failed')
                logger.error(f"Installation failed: {error_msg}")
                raise HTTPException(
                    status_code=400,
                    detail=error_msg
                )

            # Register in installed_packs table
            capability_id = result.get('capability_id')
            if capability_id:
                try:
                    # Read manifest for metadata
                    target_dir = Path(result.get('target_dir'))
                    manifest_path = target_dir / "manifest.yaml"

                    pack_metadata = {}
                    if manifest_path.exists():
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            manifest = yaml.safe_load(f)
                            pack_metadata = {
                                'side_effect_level': manifest.get('side_effect_level'),
                                'installed_from_file': True,
                                'version': result.get('version')
                            }

                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO installed_packs (pack_id, installed_at, enabled, metadata)
                            VALUES (?, ?, 1, ?)
                        ''', (
                            capability_id,
                            datetime.utcnow().isoformat(),
                            json.dumps(pack_metadata)
                        ))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to register pack in database: {e}")

            return {
                "success": True,
                "capability_id": capability_id,
                "version": result.get('version'),
                "message": f"Successfully installed {capability_id} v{result.get('version')}",
                "warnings": result.get('warnings', [])
            }

        finally:
            if tmp_path.exists():
                tmp_path.unlink()

    except HTTPException:
        raise
    except ImportError as e:
        logger.error(f"Import error in install_from_file: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import capability installer: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Installation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Installation failed: {str(e)}"
        )

