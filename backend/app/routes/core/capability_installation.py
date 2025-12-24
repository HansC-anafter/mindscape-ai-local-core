"""
Capability Installation API Routes

Provides endpoints for installing capability packs from .mindpack files.
"""

import logging
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

try:
    from app.services.capability_installer import CapabilityInstaller
except ImportError:
    # Fallback for different import paths
    try:
        from backend.app.services.capability_installer import CapabilityInstaller
    except ImportError:
        CapabilityInstaller = None

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/capabilities", tags=["capability-installation"])


class InstallationResult(BaseModel):
    """Installation result model"""
    success: bool
    capability_code: Optional[str] = None
    installed: Dict[str, List[str]] = {}
    warnings: List[str] = []
    errors: List[str] = []
    missing_dependencies: Optional[Dict[str, List[str]]] = None
    message: str = ""


@router.post("/install", response_model=InstallationResult, status_code=status.HTTP_200_OK)
async def install_capability_from_mindpack(
    file: UploadFile = File(..., description=".mindpack file to install")
):
    """
    Install a capability pack from a .mindpack file

    Args:
        file: Uploaded .mindpack file

    Returns:
        Installation result with installed components and any warnings/errors
    """
    # Validate file extension
    if not file.filename.endswith('.mindpack'):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File must be a .mindpack file"
        )

    # Save uploaded file to temporary location
    with tempfile.NamedTemporaryFile(delete=False, suffix='.mindpack') as tmp_file:
        try:
            # Write uploaded content
            content = await file.read()
            tmp_file.write(content)
            tmp_file.flush()
            tmp_path = Path(tmp_file.name)

            # Initialize installer
            # In Docker: /app/backend/app/routes/core/capability_installation.py -> /app
            # In local: backend/app/routes/core/capability_installation.py -> workspace root
            current_file = Path(__file__).resolve()
            if str(current_file).startswith('/app'):
                # Docker environment
                local_core_root = Path('/app')
            else:
                # Local environment - go up from backend/app/routes/core/ to workspace root
                local_core_root = current_file.parent.parent.parent.parent.parent
            installer = CapabilityInstaller(local_core_root=local_core_root)

            # Install capability
            success, result = installer.install_from_mindpack(tmp_path, validate=True)

            # Build response
            if success:
                playbook_count = len(result.get("installed", {}).get("playbooks", []))
                tool_count = len(result.get("installed", {}).get("tools", []))
                service_count = len(result.get("installed", {}).get("services", []))

                # Build message with dependency information
                message_parts = [
                    f"Successfully installed capability '{result['capability_code']}': "
                    f"{playbook_count} playbooks, {tool_count} tools, {service_count} services"
                ]

                missing_deps = result.get("missing_dependencies", {})
                if missing_deps:
                    dep_parts = []
                    if missing_deps.get("external_tools"):
                        dep_parts.append(f"{len(missing_deps['external_tools'])} external tools")
                    if missing_deps.get("external_services"):
                        dep_parts.append(f"{len(missing_deps['external_services'])} external services")
                    if missing_deps.get("api_keys"):
                        dep_parts.append(f"{len(missing_deps['api_keys'])} API keys")

                    if dep_parts:
                        message_parts.append(f"Note: {', '.join(dep_parts)} may need to be configured separately")

                message = " ".join(message_parts)

                return InstallationResult(
                    success=True,
                    capability_code=result.get("capability_code"),
                    installed=result.get("installed", {}),
                    warnings=result.get("warnings", []),
                    errors=result.get("errors", []),
                    missing_dependencies=result.get("missing_dependencies"),
                    message=message
                )
            else:
                error_msg = "; ".join(result.get("errors", ["Unknown error"]))
                return InstallationResult(
                    success=False,
                    capability_code=result.get("capability_code"),
                    installed=result.get("installed", {}),
                    warnings=result.get("warnings", []),
                    errors=result.get("errors", []),
                    message=f"Installation failed: {error_msg}"
                )

        except Exception as e:
            logger.error(f"Failed to install capability: {e}", exc_info=True)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Installation failed: {str(e)}"
            )
        finally:
            # Clean up temporary file
            try:
                tmp_path.unlink()
            except Exception:
                pass


@router.get("/installed", response_model=Dict[str, List[Dict]])
async def list_installed_capabilities():
    """
    List all installed capability packs

    Returns:
        Dictionary with installed capabilities information
    """
    try:
        # Determine paths
        current_file = Path(__file__).resolve()
        if '/app/backend' in str(current_file):
            # Docker environment
            local_core_root = Path('/app')
        else:
            # Local environment
            local_core_root = current_file.parent.parent.parent.parent.parent

        capabilities_dir = local_core_root / "backend" / "app" / "capabilities"

        installed = []
        if capabilities_dir.exists():
            for cap_dir in capabilities_dir.iterdir():
                if cap_dir.is_dir():
                    manifest_path = cap_dir / "manifest.yaml"
                    if manifest_path.exists():
                        try:
                            import yaml
                            with open(manifest_path, 'r', encoding='utf-8') as f:
                                manifest = yaml.safe_load(f)

                            # Count components
                            playbooks = manifest.get('playbooks', [])
                            tools_dir = cap_dir / "tools"
                            services_dir = cap_dir / "services"

                            installed.append({
                                "code": manifest.get('code', cap_dir.name),
                                "display_name": manifest.get('display_name', cap_dir.name),
                                "version": manifest.get('version', 'unknown'),
                                "type": manifest.get('type', 'unknown'),
                                "playbook_count": len(playbooks),
                                "tool_count": len(list(tools_dir.glob("*.py"))) if tools_dir.exists() else 0,
                                "service_count": len(list(services_dir.glob("*.py"))) if services_dir.exists() else 0,
                            })
                        except Exception as e:
                            logger.warning(f"Failed to read manifest for {cap_dir.name}: {e}")

        return {"capabilities": installed}

    except Exception as e:
        logger.error(f"Failed to list installed capabilities: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list capabilities: {str(e)}"
        )

