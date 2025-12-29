"""
Capability Packs API

Handles installation and management of capability packs.
Provides registry API for listing, enabling, and disabling packs.

Packs are loaded from /packs/*.yaml files or plugin registry.
"""

from fastapi import APIRouter, HTTPException, UploadFile, File, Form, Query
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
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

router = APIRouter(prefix="/api/v1/capability-packs", tags=["Capability Packs"])

# Database helper
def get_db_path():
    if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
        return '/app/data/mindscape.db'
    base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
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


def _load_manifest_file(manifest_path: Path) -> Optional[Dict[str, Any]]:
    try:
        with open(manifest_path, 'r', encoding='utf-8') as f:
            pack_meta = yaml.safe_load(f)
            if pack_meta and isinstance(pack_meta, dict):
                pack_meta['_file_path'] = str(manifest_path)
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
                logger.warning(f"Packs directory not found. Tried: {base_dir / 'packs'}, {Path('/app/backend/packs')}, {base_dir / 'backend' / 'packs'}")
                return packs

    # Scan for .yaml files
    for pack_file in packs_dir.glob("*.yaml"):
        meta = _load_manifest_file(pack_file)
        if meta:
            packs.append(meta)

    # Scan installed capabilities from backend/app/capabilities/
    # In Docker: /app/backend/app/routes/core/capability_packs.py -> /app/backend/app/capabilities
    # In local: backend/app/routes/core/capability_packs.py -> backend/app/capabilities
    capabilities_dir = base_dir / "app" / "capabilities"
    if not capabilities_dir.exists():
        # Try alternative paths
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
                    "ui_components": meta.get("ui_components", []),  # Include UI components
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
        with get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('SELECT pack_id, installed_at, metadata FROM installed_packs')
            for row in cursor.fetchall():
                import json
                metadata = json.loads(row['metadata']) if row['metadata'] else {}
                installed_metadata[row['pack_id']] = {
                    'installed_at': row['installed_at'],
                    'version': metadata.get('version', '1.0.0')
                }

        packs = []
        for pack_meta in pack_metas:
            pack_id = pack_meta.get('id')
            if not pack_id:
                logger.warning(f"Pack metadata missing 'id' field: {pack_meta.get('_file_path', 'unknown')}")
                continue

            installed_info = installed_metadata.get(pack_id, {})

            # 处理 tools 字段：如果是字典列表，提取工具名称
            tools_raw = pack_meta.get('tools', [])
            tools_list = []
            if isinstance(tools_raw, list):
                for tool in tools_raw:
                    if isinstance(tool, str):
                        tools_list.append(tool)
                    elif isinstance(tool, dict):
                        # 从字典中提取工具名称
                        tool_name = tool.get('name') or tool.get('id') or tool.get('tool')
                        if tool_name:
                            tools_list.append(tool_name)

            packs.append(PackResponse(
                id=pack_id,
                name=pack_meta.get('name', pack_id),
                description=pack_meta.get('description', ''),
                enabled_by_default=pack_meta.get('enabled_by_default', False),
                enabled=pack_id in enabled_ids,
                installed=pack_id in installed_ids,
                routes=pack_meta.get('routes', []),
                playbooks=pack_meta.get('playbooks', []),
                tools=tools_list,
                version=installed_info.get('version') or pack_meta.get('version', '1.0.0'),
                installed_at=installed_info.get('installed_at')
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
            pack_id = pack_meta.get('id')
            if pack_id and pack_id in installed_ids:
                installed_capabilities.append({
                    'id': pack_id,
                    'code': pack_meta.get('code', pack_id),  # Use code from meta if available
                    'display_name': pack_meta.get('name', pack_id),
                    'version': pack_meta.get('version', '1.0.0'),
                    'description': pack_meta.get('description', ''),
                    'scope': pack_meta.get('scope', 'global'),
                    'ui_components': pack_meta.get('ui_components', [])  # Include UI components info
                })

        return installed_capabilities
    except Exception as e:
        logger.error(f"Failed to list installed capabilities: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to list installed capabilities: {str(e)}")


@router.get("/installed-capabilities/{capability_code}/ui-components", response_model=List[Dict[str, Any]])
async def get_capability_ui_components(capability_code: str):
    """
    Get UI components information for an installed capability

    Returns UI components metadata from the capability's manifest.
    Frontend uses this to dynamically load UI components.

    Boundary: This API only reads manifest metadata, does not serve component code.
    Component code must be installed via CapabilityInstaller, not hardcoded.
    """
    try:
        # Get all packs
        pack_metas = _scan_pack_yaml_files()

        # Find the capability
        pack_meta = next((p for p in pack_metas if p.get('id') == capability_code), None)

        if not pack_meta:
            raise HTTPException(status_code=404, detail=f"Capability '{capability_code}' not found")

        # Check if installed
        installed_ids = _get_installed_pack_ids()
        if capability_code not in installed_ids:
            raise HTTPException(status_code=404, detail=f"Capability '{capability_code}' is not installed")

        # Return UI components from manifest
        ui_components = pack_meta.get('ui_components', [])

        # Format response with component metadata
        formatted_components = []
        for component in ui_components:
            # Component file should be at: web-console/src/app/capabilities/{capability_code}/components/{filename}
            # Remove .tsx/.ts extension for dynamic import
            component_filename = Path(component.get("path", "")).name
            component_name = component_filename.replace('.tsx', '').replace('.ts', '')

            formatted_components.append({
                'code': component.get('code'),
                'path': component.get('path'),
                'description': component.get('description', ''),
                'export': component.get('export', 'default'),
                'artifact_types': component.get('artifact_types', []),
                'playbook_codes': component.get('playbook_codes', []),
                'import_path': f'@/app/capabilities/{capability_code}/components/{component_name}'
            })

        return formatted_components
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get UI components for capability {capability_code}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get UI components: {str(e)}")


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
        app_dir = current_file.parent.parent
        backend_dir = app_dir.parent

        # Resolve workspace root directory for CapabilityInstaller
        local_core_root = current_file.parent.parent.parent.parent.parent

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
            installer = CapabilityInstaller(local_core_root=local_core_root)
            success, install_result = installer.install_from_mindpack(tmp_path, validate=True)

            # Convert result format to match expected format
            if not success:
                error_msg = install_result.get('errors', ['Installation failed'])
                if isinstance(error_msg, list) and error_msg:
                    error_msg = error_msg[0]
                elif not isinstance(error_msg, str):
                    error_msg = 'Installation failed'
                result = {'success': False, 'error': error_msg}
            else:
                capability_code = install_result.get('capability_code', 'grant_scout')
                correct_backend_dir = local_core_root / 'backend'
                result = {
                    'success': True,
                    'capability_id': capability_code,
                    'version': '1.0.0',
                    'target_dir': str(correct_backend_dir / 'app' / 'capabilities' / capability_code)
                }

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


# ============================================
# Cloud Pack Installation (From Remote Provider)
# ============================================

class InstallFromCloudRequest(BaseModel):
    """Request model for installing pack from cloud provider"""
    pack_ref: str = Field(..., description="Pack reference in format 'provider_id:code@version'")
    provider_id: str = Field(..., description="Provider ID to download from")
    verify_checksum: bool = Field(True, description="Whether to verify SHA256 checksum")


@router.post("/install-from-cloud", response_model=Dict[str, Any])
async def install_from_cloud(
    request: InstallFromCloudRequest,
    profile_id: str = Query("default-user", description="User profile ID for role mapping")
):
    """
    Install capability pack from cloud provider

    Downloads pack from configured cloud provider and installs it locally.
    Supports any provider that implements the CloudProvider interface.

    Flow:
    1. Get provider instance from CloudExtensionManager
    2. Get download link from provider
    3. Download pack file
    4. Verify checksum (if enabled)
    5. Install using CapabilityInstaller
    """
    try:
        import sys
        from pathlib import Path

        # Get backend directory and add to sys.path
        current_file = Path(__file__).resolve()
        app_dir = current_file.parent.parent
        backend_dir = app_dir.parent
        local_core_root = current_file.parent.parent.parent.parent.parent

        backend_dir_str = str(backend_dir)
        if backend_dir_str not in sys.path:
            sys.path.insert(0, backend_dir_str)

        from app.services.capability_installer import CapabilityInstaller
        from app.services.cloud_extension_manager import CloudExtensionManager
        from app.services.pack_download_service import get_pack_download_service
        from app.services.system_settings_store import SystemSettingsStore
        from app.routes.core.cloud_providers import get_cloud_manager

        # Get cloud extension manager (with auto-loading from settings)
        cloud_manager = get_cloud_manager()

        # Get provider instance
        provider = cloud_manager.get_provider(request.provider_id)
        if not provider:
            raise HTTPException(
                status_code=404,
                detail=f"Provider '{request.provider_id}' not found. Please configure it first."
            )

        if not provider.is_configured():
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{request.provider_id}' is not configured. Please configure it first."
            )

        # Check if provider supports get_download_link
        if not hasattr(provider, 'get_download_link'):
            raise HTTPException(
                status_code=400,
                detail=f"Provider '{request.provider_id}' does not support pack downloads"
            )

        # Download pack from cloud provider
        download_service = get_pack_download_service()
        success, pack_file, error_msg = await download_service.download_pack(
            provider=provider,
            pack_ref=request.pack_ref,
            verify_checksum=request.verify_checksum
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail=f"Failed to download pack: {error_msg}"
            )

        if not pack_file:
            raise HTTPException(
                status_code=500,
                detail="Download succeeded but pack file not returned"
            )

        try:
            # Install pack using CapabilityInstaller
            installer = CapabilityInstaller(local_core_root=local_core_root)
            install_success, install_result = installer.install_from_mindpack(
                pack_file, validate=True
            )

            if not install_success:
                error_msg = install_result.get('errors', ['Installation failed'])
                if isinstance(error_msg, list) and error_msg:
                    error_msg = error_msg[0]
                elif not isinstance(error_msg, str):
                    error_msg = 'Installation failed'
                raise HTTPException(
                    status_code=400,
                    detail=error_msg
                )

            capability_code = install_result.get('capability_code')
            correct_backend_dir = local_core_root / 'backend'

            # Register in installed_packs table
            if capability_code:
                try:
                    target_dir = correct_backend_dir / 'app' / 'capabilities' / capability_code
                    manifest_path = target_dir / "manifest.yaml"

                    pack_metadata = {
                        'installed_from_cloud': True,
                        'provider_id': request.provider_id,
                        'pack_ref': request.pack_ref,
                        'version': install_result.get('version', '1.0.0')
                    }

                    if manifest_path.exists():
                        with open(manifest_path, 'r', encoding='utf-8') as f:
                            manifest = yaml.safe_load(f)
                            pack_metadata.update({
                                'side_effect_level': manifest.get('side_effect_level'),
                                'version': manifest.get('version', pack_metadata['version'])
                            })

                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute('''
                            INSERT OR REPLACE INTO installed_packs (pack_id, installed_at, enabled, metadata)
                            VALUES (?, ?, 1, ?)
                        ''', (
                            capability_code,
                            datetime.utcnow().isoformat(),
                            json.dumps(pack_metadata)
                        ))
                        conn.commit()
                except Exception as e:
                    logger.warning(f"Failed to register pack in database: {e}")

            return {
                "success": True,
                "capability_id": capability_code,
                "version": pack_metadata.get('version', '1.0.0'),
                "message": f"Successfully installed {capability_code} from {request.provider_id}",
                "warnings": install_result.get('warnings', []),
                "provider_id": request.provider_id,
                "pack_ref": request.pack_ref
            }

        finally:
            # Clean up downloaded file
            if pack_file and pack_file.exists():
                try:
                    pack_file.unlink()
                except Exception as e:
                    logger.warning(f"Failed to clean up temporary pack file: {e}")

    except HTTPException:
        raise
    except ImportError as e:
        logger.error(f"Import error in install_from_cloud: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to import required modules: {str(e)}"
        )
    except Exception as e:
        logger.error(f"Cloud installation failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Cloud installation failed: {str(e)}"
        )

