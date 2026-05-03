"""
Publish Service API Routes

Provider-neutral publish service interface.
"""

import logging
from typing import Optional, Dict, Any
from fastapi import APIRouter, HTTPException, Depends, status, UploadFile, File
from pydantic import BaseModel, Field
import httpx

from ...services.system_settings_store import SystemSettingsStore
from ...models.system_settings import SettingType
from ...services.tool_registry import ToolRegistryService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/publish-service", tags=["publish-service"])


class PublishServiceConfig(BaseModel):
    """Publish service configuration."""
    api_url: str = Field(..., description="Publish service API URL")
    api_key: str = Field(..., description="API key for authentication")
    enabled: bool = Field(True, description="Whether the publish service is enabled")
    provider_id: Optional[str] = Field(None, description="Optional provider ID")
    storage_backend: Optional[str] = Field(None, description="Optional storage backend: gcs, s3, or r2")
    storage_config: Optional[Dict[str, Any]] = Field(None, description="Optional storage configuration")


class PublishRequest(BaseModel):
    """Publish request."""
    content_type: str = Field(..., description="Content type: playbook or capability")
    content_id: str = Field(..., description="Content ID, for example example_pack.workflow")
    version: str = Field(..., description="Version")
    options: Optional[Dict[str, Any]] = Field(None, description="Optional publish options")


class PublishResponse(BaseModel):
    """Publish response."""
    success: bool
    publish_id: Optional[str] = None
    message: str
    version: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class TestConnectionResponse(BaseModel):
    """Connection test response."""
    success: bool
    message: str


def get_settings_store() -> SystemSettingsStore:
    """Dependency to get settings store"""
    return SystemSettingsStore()


def get_tool_registry() -> ToolRegistryService:
    """Dependency to get tool registry"""
    return ToolRegistryService()


def get_publish_service_config(
    settings_store: SystemSettingsStore = Depends(get_settings_store),
    tool_registry: ToolRegistryService = Depends(get_tool_registry)
) -> Optional[PublishServiceConfig]:
    """
    Resolve publish service configuration.

    Returns:
        PublishServiceConfig or None if not configured.
    """
    profile_id = 'default-profile'  # TODO: Get from auth context

    publish_types = ['publish_custom', 'publish_private_cloud', 'publish_dropbox', 'publish_google_drive']
    publish_connections = []

    for pub_type in publish_types:
        try:
            conns = tool_registry.get_connections_by_tool_type(profile_id, pub_type)
            if conns:
                publish_connections.extend(conns)
        except Exception:
            continue

    if publish_connections:
        active_conn = next((c for c in publish_connections if c.is_active), None)
        if active_conn:
            conn = active_conn
            api_url = conn.base_url or ''
            if not api_url and conn.config:
                api_url = conn.config.get('api_url', '')

            return PublishServiceConfig(
                api_url=api_url,
                api_key=conn.api_key or '',
                enabled=conn.is_active,
                provider_id=conn.config.get('provider_id') if conn.config else None,
                storage_backend=conn.config.get('storage_backend') if conn.config else None,
                storage_config=conn.config.get('storage_config') if conn.config else None
            )

    config = settings_store.get("publish_service", default=None)
    if config is None:
        return None

    if not isinstance(config, dict):
        return None

    return PublishServiceConfig(**config)


@router.get("/config", response_model=Optional[PublishServiceConfig])
async def get_config(
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """Get publish service configuration."""
    config = get_publish_service_config(settings_store)
    return config


@router.put("/config", response_model=PublishServiceConfig)
async def update_config(
    config: PublishServiceConfig,
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """Update publish service configuration."""
    try:
        settings_store.set_setting(
            key="publish_service",
            value=config.model_dump(),
            value_type=SettingType.JSON,
            category="cloud"
        )
        logger.info(f"Publish service config updated: {config.api_url}")
        return config
    except Exception as e:
        logger.error(f"Failed to update publish service config: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to update config: {str(e)}")


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """Test publish service connection."""
    config = get_publish_service_config(settings_store)
    if not config:
        return TestConnectionResponse(
            success=False,
            message="Publish service is not configured"
        )

    if not config.enabled:
        return TestConnectionResponse(
            success=False,
            message="Publish service is disabled"
        )

    try:
        test_url = f"{config.api_url.rstrip('/')}/health"

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                test_url,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 200:
                return TestConnectionResponse(
                    success=True,
                    message="Connection succeeded"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message=f"Connection failed: HTTP {response.status_code}"
                )
    except httpx.TimeoutException:
        return TestConnectionResponse(
            success=False,
            message="Connection timed out"
        )
    except Exception as e:
        logger.error(f"Failed to test connection: {e}", exc_info=True)
        return TestConnectionResponse(
            success=False,
            message=f"Connection failed: {str(e)}"
        )


@router.post("/publish", response_model=PublishResponse)
async def publish_content(
    request: PublishRequest,
    package_file: UploadFile = File(...),
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """
    Publish content to the configured publish service.

    This is a provider-neutral HTTP proxy.
    """
    config = get_publish_service_config(settings_store)
    if not config:
        raise HTTPException(
            status_code=400,
            detail="Publish service is not configured"
        )

    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail="Publish service is disabled"
        )

    try:
        file_content = await package_file.read()

        publish_url = f"{config.api_url.rstrip('/')}/api/v1/publish"

        files = {
            'package_file': (package_file.filename, file_content, package_file.content_type or 'application/zip')
        }
        data = {
            'content_type': request.content_type,
            'content_id': request.content_id,
            'version': request.version
        }
        if request.options:
            import json
            data['options'] = json.dumps(request.options)

        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                publish_url,
                files=files,
                data=data,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                }
            )

            if response.status_code == 200 or response.status_code == 201:
                result_data = response.json()
                return PublishResponse(
                    success=result_data.get("success", True),
                    publish_id=result_data.get("publish_id"),
                    message=result_data.get("message", "Publish succeeded"),
                    version=result_data.get("version", request.version),
                    url=result_data.get("url"),
                    error=result_data.get("error")
                )
            else:
                error_msg = response.text
                try:
                    error_data = response.json()
                    error_msg = error_data.get("detail", error_msg)
                    if isinstance(error_msg, dict):
                        error_msg = error_msg.get("message", str(error_msg))
                except:
                    pass

                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Publish service error: {error_msg}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Publish service response timed out"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to publish: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Publish failed: {str(e)}"
        )


@router.get("/history")
async def get_publish_history(
    limit: int = 50,
    offset: int = 0,
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """Get publish history from the configured publish service."""
    config = get_publish_service_config(settings_store)
    if not config:
        raise HTTPException(
            status_code=400,
            detail="Publish service is not configured"
        )

    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail="Publish service is disabled"
        )

    try:
        history_url = f"{config.api_url.rstrip('/')}/api/v1/publish/history"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                history_url,
                params={"limit": limit, "offset": offset},
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to query publish history: {response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Publish service response timed out"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get publish history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query publish history: {str(e)}"
        )


@router.get("/publish/{publish_id}/status")
async def get_publish_status(
    publish_id: str,
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """Get publish status from the configured publish service."""
    config = get_publish_service_config(settings_store)
    if not config:
        raise HTTPException(
            status_code=400,
            detail="Publish service is not configured"
        )

    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail="Publish service is disabled"
        )

    try:
        status_url = f"{config.api_url.rstrip('/')}/api/v1/publish/{publish_id}/status"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                status_url,
                headers={
                    "Authorization": f"Bearer {config.api_key}",
                    "Content-Type": "application/json"
                }
            )

            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to query publish status: {response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Publish service response timed out"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get publish status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"Failed to query publish status: {str(e)}"
        )
