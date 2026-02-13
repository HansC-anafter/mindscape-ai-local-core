"""
Runtime Environments API Routes

CRUD endpoints for managing runtime environments (e.g., Site-Hub, Semantic-Hub).
Supports user-defined runtime configurations with authentication.
"""

import uuid
import logging
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, Body
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy.orm import Session

from ...models.runtime_environment import RuntimeEnvironment
from ...services.runtime_auth_service import RuntimeAuthService
from ...services.runtime_discovery_service import (
    RuntimeDiscoveryService,
    DiscoveryResult,
)

# Import database session
try:
    from ...database.session import get_db_postgres as get_db
except ImportError:
    try:
        from ...database import get_db_postgres as get_db
    except ImportError:
        # Fallback: use dependency injection
        from mindscape.di.providers import get_db_session as get_db

# Import auth dependencies
try:
    from ...auth import get_current_user
    from ...models.user import User
except ImportError:
    # Fallback for development
    from typing import Any

    async def get_current_user() -> Any:
        """Placeholder for development"""
        return type("User", (), {"id": "dev-user"})()

    User = Any

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/runtime-environments", tags=["runtime-environments"])

auth_service = RuntimeAuthService()
discovery_service = RuntimeDiscoveryService()


# Pydantic models for request/response
class CreateRuntimeEnvironmentRequest(BaseModel):
    """Request model for creating a runtime environment"""

    name: str = Field(..., description="Runtime name (user-defined)")
    description: Optional[str] = Field(None, description="Runtime description")
    icon: Optional[str] = Field(None, description="Icon (emoji or identifier)")
    config_url: str = Field(..., description="Configuration page URL")
    auth_type: str = Field(
        default="none",
        description="Authentication type: 'api_key', 'oauth2', or 'none'",
    )
    auth_config: Optional[Dict[str, Any]] = Field(
        None, description="Authentication configuration"
    )
    supports_dispatch: bool = Field(
        default=True, description="Support Dispatch Workspace"
    )
    supports_cell: bool = Field(default=True, description="Support Cell Workspace")
    recommended_for_dispatch: bool = Field(
        default=False, description="Recommended for Dispatch"
    )


class UpdateRuntimeEnvironmentRequest(BaseModel):
    """Request model for updating a runtime environment"""

    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    config_url: Optional[str] = None
    auth_type: Optional[str] = None
    auth_config: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    supports_dispatch: Optional[bool] = None
    supports_cell: Optional[bool] = None
    recommended_for_dispatch: Optional[bool] = None


class DiscoveryScanRequest(BaseModel):
    """Request model for scanning a folder for runtime configuration"""

    path: str = Field(..., description="Local folder path to scan")
    runtime_type: str = Field(
        default="comfyui", description="Type of runtime to scan for"
    )


@router.get("")
async def list_runtime_environments(
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    """
    List all runtime environments for the current user.

    Returns:
        Dictionary with 'runtimes' list containing all user's runtime environments
        plus the default Local-Core runtime
    """
    try:
        # Manually get db session (get_db is a wrapped generator, FastAPI can't auto-detect)
        db_gen = get_db()
        db = next(db_gen)
        # Get user's runtime environments
        user_runtimes = (
            db.query(RuntimeEnvironment)
            .filter(RuntimeEnvironment.user_id == current_user.id)
            .all()
        )

        # Build response with Local-Core as default
        runtimes = [
            {
                "id": "local-core",
                "name": "Local-Core Runtime",
                "description": "本地執行環境，預設啟用",
                "icon": "💻",
                "status": "active",
                "is_default": True,
                "config_url": None,
                "auth_type": "none",
                "supports_dispatch": True,
                "supports_cell": True,
            }
        ]

        # Add user's runtime environments (without sensitive data)
        for runtime in user_runtimes:
            runtimes.append(runtime.to_dict(include_sensitive=False))

        return {"runtimes": runtimes}

    except Exception as e:
        logger.error(f"Failed to list runtime environments: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, detail="Failed to list runtime environments"
        )


@router.post("")
async def create_runtime_environment(
    request: CreateRuntimeEnvironmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Create a new runtime environment.

    Args:
        request: Runtime environment creation request
        current_user: Current authenticated user
        db: Database session

    Returns:
        Created runtime environment (without sensitive data)
    """
    try:
        # Validate auth configuration
        if not auth_service.validate_auth_config(
            request.auth_type, request.auth_config
        ):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid authentication configuration for auth_type '{request.auth_type}'",
            )

        # Encrypt credentials if provided
        encrypted_auth_config = None
        if request.auth_config:
            encrypted_auth_config = auth_service.encrypt_credentials(
                request.auth_config
            )

        # Create runtime environment
        runtime_id = f"runtime-{uuid.uuid4().hex[:12]}"
        runtime = RuntimeEnvironment(
            id=runtime_id,
            user_id=current_user.id,
            name=request.name,
            description=request.description,
            icon=request.icon,
            config_url=request.config_url,
            auth_type=request.auth_type,
            auth_config=encrypted_auth_config,
            status="not_configured",
            is_default=False,
            supports_dispatch=request.supports_dispatch,
            supports_cell=request.supports_cell,
            recommended_for_dispatch=request.recommended_for_dispatch,
        )

        db.add(runtime)
        db.commit()
        db.refresh(runtime)

        return runtime.to_dict(include_sensitive=False)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create runtime environment: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to create runtime environment"
        )


@router.get("/{runtime_id}")
async def get_runtime_environment(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Get a specific runtime environment.

    Args:
        runtime_id: Runtime environment ID (or "local-core" for default)
        current_user: Current authenticated user
        db: Database session

    Returns:
        Runtime environment details (without sensitive data)
    """
    try:
        # Handle Local-Core special case
        if runtime_id == "local-core":
            return {
                "id": "local-core",
                "name": "Local-Core Runtime",
                "description": "本地執行環境，預設啟用",
                "icon": "💻",
                "status": "active",
                "is_default": True,
                "config_url": None,
                "auth_type": "none",
                "supports_dispatch": True,
                "supports_cell": True,
            }

        # Get user's runtime environment
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.id == runtime_id,
                RuntimeEnvironment.user_id == current_user.id,
            )
            .first()
        )

        if not runtime:
            raise HTTPException(
                status_code=404, detail=f"Runtime environment '{runtime_id}' not found"
            )

        return runtime.to_dict(include_sensitive=False)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get runtime environment: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get runtime environment")


@router.put("/{runtime_id}")
async def update_runtime_environment(
    runtime_id: str,
    request: UpdateRuntimeEnvironmentRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """
    Update a runtime environment.

    Args:
        runtime_id: Runtime environment ID
        request: Update request
        current_user: Current authenticated user
        db: Database session

    Returns:
        Updated runtime environment (without sensitive data)
    """
    try:
        # Local-Core cannot be updated
        if runtime_id == "local-core":
            raise HTTPException(
                status_code=400,
                detail="Cannot update Local-Core runtime (system default)",
            )

        # Get user's runtime environment
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.id == runtime_id,
                RuntimeEnvironment.user_id == current_user.id,
            )
            .first()
        )

        if not runtime:
            raise HTTPException(
                status_code=404, detail=f"Runtime environment '{runtime_id}' not found"
            )

        # Update fields
        if request.name is not None:
            runtime.name = request.name
        if request.description is not None:
            runtime.description = request.description
        if request.icon is not None:
            runtime.icon = request.icon
        if request.config_url is not None:
            runtime.config_url = request.config_url
        if request.status is not None:
            runtime.status = request.status
        if request.supports_dispatch is not None:
            runtime.supports_dispatch = request.supports_dispatch
        if request.supports_cell is not None:
            runtime.supports_cell = request.supports_cell
        if request.recommended_for_dispatch is not None:
            runtime.recommended_for_dispatch = request.recommended_for_dispatch

        # Update authentication if provided
        if request.auth_type is not None:
            runtime.auth_type = request.auth_type
            if request.auth_config is not None:
                # Validate and encrypt
                if not auth_service.validate_auth_config(
                    request.auth_type, request.auth_config
                ):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid authentication configuration for auth_type '{request.auth_type}'",
                    )
                runtime.auth_config = auth_service.encrypt_credentials(
                    request.auth_config
                )

        db.commit()
        db.refresh(runtime)

        return runtime.to_dict(include_sensitive=False)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update runtime environment: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to update runtime environment"
        )


@router.delete("/{runtime_id}")
async def delete_runtime_environment(
    runtime_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, str]:
    """
    Delete a runtime environment.

    Args:
        runtime_id: Runtime environment ID
        current_user: Current authenticated user
        db: Database session

    Returns:
        Success message
    """
    try:
        # Local-Core cannot be deleted
        if runtime_id == "local-core":
            raise HTTPException(
                status_code=400,
                detail="Cannot delete Local-Core runtime (system default)",
            )

        # Get user's runtime environment
        runtime = (
            db.query(RuntimeEnvironment)
            .filter(
                RuntimeEnvironment.id == runtime_id,
                RuntimeEnvironment.user_id == current_user.id,
            )
            .first()
        )

        if not runtime:
            raise HTTPException(
                status_code=404, detail=f"Runtime environment '{runtime_id}' not found"
            )

        # TODO: Check if runtime is in use by any workspace
        # If so, prevent deletion or require confirmation

        db.delete(runtime)
        db.commit()

        return {"message": f"Runtime environment '{runtime_id}' deleted successfully"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete runtime environment: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(
            status_code=500, detail="Failed to delete runtime environment"
        )


@router.post("/discovery/scan", response_model=DiscoveryResult)
async def scan_runtime(
    request: DiscoveryScanRequest, current_user: User = Depends(get_current_user)
):
    """
    Scan a local folder for runtime configuration.

    This endpoint helps users automatically configure local runtimes
    by identifying paths, ports, and metadata from a selected folder.
    """
    try:
        result = discovery_service.scan_folder(request.path, request.runtime_type)
        return result
    except Exception as e:
        logger.error(f"Discovery scan failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Discovery scan failed: {str(e)}")
