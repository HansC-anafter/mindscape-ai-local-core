"""
Configuration API routes
Handles backend configuration and user settings

Note: remote_crs mode is implemented via adapter pattern.
If no remote_crs adapter is enabled, remote_crs mode will return 501.
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Dict, Any, Optional

from ...models.config import UpdateBackendConfigRequest, UserConfig
from ...services.config_store import ConfigStore
from ...services.backend_manager import BackendManager

router = APIRouter(prefix="/api/v1/config", tags=["config"])

# Initialize stores
config_store = ConfigStore()
backend_manager = BackendManager(config_store=config_store)


def _check_remote_crs_adapter() -> bool:
    """
    Check if remote_crs adapter is available

    Returns:
        True if adapter is available, False otherwise
    """
    # TODO: Check if remote_crs adapter is registered
    # For now, return False (adapter not implemented yet)
    # This will be implemented in a later phase when adapter system is ready
    return False


@router.get("/backend", response_model=Dict[str, Any])
async def get_backend_config(profile_id: str = Query(..., description="Profile ID")):
    """Get current backend configuration"""
    try:
        config = config_store.get_or_create_config(profile_id)

        # Get available backends info
        available_backends = backend_manager.get_available_backends()

        # Filter out remote_crs if adapter is not available
        if not _check_remote_crs_adapter():
            available_backends = {
                k: v for k, v in available_backends.items()
                if k != "remote_crs"
            }

        return {
            "profile_id": profile_id,
            "current_mode": config.agent_backend.mode,
            "remote_crs_url": config.agent_backend.remote_crs_url if _check_remote_crs_adapter() else None,
            "remote_crs_configured": bool(config.agent_backend.remote_crs_url and config.agent_backend.remote_crs_token) if _check_remote_crs_adapter() else False,
            "openai_api_key_configured": bool(config.agent_backend.openai_api_key),
            "anthropic_api_key_configured": bool(config.agent_backend.anthropic_api_key),
            "available_backends": available_backends,
            "remote_crs_adapter_available": _check_remote_crs_adapter()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get config: {str(e)}")


@router.put("/backend", response_model=Dict[str, Any])
async def update_backend_config(
    profile_id: str = Query(..., description="Profile ID"),
    request: UpdateBackendConfigRequest = None
):
    """Update backend configuration"""
    if not request:
        raise HTTPException(status_code=400, detail="Update request required")

    try:
        # Validate mode - only allow local if adapter not available
        if request.mode == "remote_crs" and not _check_remote_crs_adapter():
            raise HTTPException(
                status_code=501,
                detail="remote_crs mode requires a remote_crs adapter to be installed and configured. "
                       "Please install the remote_crs adapter pack or use 'local' mode."
            )

        if request.mode not in ["local", "remote_crs"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid mode. Must be 'local' or 'remote_crs'"
            )

        # If setting remote mode, validate credentials
        if request.mode == "remote_crs":
            if not _check_remote_crs_adapter():
                raise HTTPException(
                    status_code=501,
                    detail="remote_crs adapter is not available. Please install and configure the remote_crs adapter pack."
                )

            if not request.remote_crs_url:
                raise HTTPException(
                    status_code=400,
                    detail="remote_crs_url is required for remote_crs mode"
                )
            # Token is optional if already configured (to allow keeping existing token)
            # But if URL is new or changed, token is required
            existing_config = config_store.get_config(profile_id)
            if existing_config and existing_config.agent_backend.remote_crs_url == request.remote_crs_url:
                # URL unchanged, token can be empty to keep existing
                if not request.remote_crs_token:
                    request.remote_crs_token = existing_config.agent_backend.remote_crs_token
            elif not request.remote_crs_token:
                # New URL or URL changed, token is required
                raise HTTPException(
                    status_code=400,
                    detail="remote_crs_token is required for remote_crs mode when URL is new or changed"
                )

        # Update backend mode
        success = backend_manager.set_backend_mode(
            profile_id=profile_id,
            mode=request.mode,
            remote_crs_url=request.remote_crs_url if _check_remote_crs_adapter() else None,
            remote_crs_token=request.remote_crs_token if _check_remote_crs_adapter() else None,
            openai_api_key=request.openai_api_key,
            anthropic_api_key=request.anthropic_api_key
        )

        if not success:
            raise HTTPException(
                status_code=400,
                detail="Failed to set backend mode. Please check your configuration."
            )

        # Return updated config
        config = config_store.get_config(profile_id)
        return {
            "profile_id": profile_id,
            "current_mode": config.agent_backend.mode,
            "remote_crs_url": config.agent_backend.remote_crs_url if (request.mode == "remote_crs" and _check_remote_crs_adapter()) else None,
            "remote_crs_configured": bool(config.agent_backend.remote_crs_url and config.agent_backend.remote_crs_token) if _check_remote_crs_adapter() else False,
            "openai_api_key_configured": bool(config.agent_backend.openai_api_key),
            "anthropic_api_key_configured": bool(config.agent_backend.anthropic_api_key),
            "message": "Backend configuration updated successfully"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")


@router.get("/backends", response_model=Dict[str, Any])
async def list_available_backends():
    """List all available backend types and their status"""
    try:
        backends = backend_manager.get_available_backends()

        # Filter out remote_crs if adapter is not available
        if not _check_remote_crs_adapter():
            backends = {
                k: v for k, v in backends.items()
                if k != "remote_crs"
            }

        return {
            "backends": backends,
            "remote_crs_adapter_available": _check_remote_crs_adapter()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to list backends: {str(e)}")

