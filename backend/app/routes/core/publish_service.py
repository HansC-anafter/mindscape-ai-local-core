"""
Publish Service API Routes
中性發佈服務接口 - 不依賴特定服務提供商
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
    """發佈服務配置模型"""
    api_url: str = Field(..., description="發佈服務 API URL")
    api_key: str = Field(..., description="API Key 用於認證")
    enabled: bool = Field(True, description="是否啟用發佈服務")
    provider_id: Optional[str] = Field(None, description="Provider ID（可選）")
    storage_backend: Optional[str] = Field(None, description="Storage 後端（gcs, s3, r2，可選）")
    storage_config: Optional[Dict[str, Any]] = Field(None, description="Storage 配置（可選）")


class PublishRequest(BaseModel):
    """發佈請求模型"""
    content_type: str = Field(..., description="內容類型：playbook 或 capability")
    content_id: str = Field(..., description="內容 ID（例如：openseo.seo_optimization）")
    version: str = Field(..., description="版本號")
    options: Optional[Dict[str, Any]] = Field(None, description="可選的發佈選項")


class PublishResponse(BaseModel):
    """發佈響應模型"""
    success: bool
    publish_id: Optional[str] = None
    message: str
    version: Optional[str] = None
    url: Optional[str] = None
    error: Optional[str] = None


class TestConnectionResponse(BaseModel):
    """測試連接響應模型"""
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
    獲取發佈服務配置

    優先從工具連接獲取，如果沒有則從系統設定獲取（向後兼容）

    Returns:
        PublishServiceConfig 或 None（如果未配置）
    """
    # 優先從工具連接獲取（publish_custom, publish_private_cloud 等）
    profile_id = 'default-profile'  # TODO: Get from auth context

    # 嘗試多種發佈目標類型
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
        # 使用第一個已啟用的發佈目標
        active_conn = next((c for c in publish_connections if c.is_active), None)
        if active_conn:
            conn = active_conn
            # 對於 Dropbox/Google Drive，需要從 config 獲取 API URL
            api_url = conn.base_url or ''
            if not api_url and conn.config:
                # Dropbox/Google Drive 可能使用不同的 API URL
                api_url = conn.config.get('api_url', '')

            return PublishServiceConfig(
                api_url=api_url,
                api_key=conn.api_key or '',
                enabled=conn.is_active,
                provider_id=conn.config.get('provider_id') if conn.config else None,
                storage_backend=conn.config.get('storage_backend') if conn.config else None,
                storage_config=conn.config.get('storage_config') if conn.config else None
            )

    # 降級：從系統設定獲取（向後兼容）
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
    """
    獲取發佈服務配置
    """
    config = get_publish_service_config(settings_store)
    return config


@router.put("/config", response_model=PublishServiceConfig)
async def update_config(
    config: PublishServiceConfig,
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """
    更新發佈服務配置
    """
    try:
        settings_store.set_setting(
            key="publish_service",
            value=config.dict(),
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
    """
    測試發佈服務連接
    """
    config = get_publish_service_config(settings_store)
    if not config:
        return TestConnectionResponse(
            success=False,
            message="發佈服務未配置"
        )

    if not config.enabled:
        return TestConnectionResponse(
            success=False,
            message="發佈服務已禁用"
        )

    try:
        # 簡單的 health check 或測試端點
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
                    message="連接成功"
                )
            else:
                return TestConnectionResponse(
                    success=False,
                    message=f"連接失敗：HTTP {response.status_code}"
                )
    except httpx.TimeoutException:
        return TestConnectionResponse(
            success=False,
            message="連接超時"
        )
    except Exception as e:
        logger.error(f"Failed to test connection: {e}", exc_info=True)
        return TestConnectionResponse(
            success=False,
            message=f"連接失敗：{str(e)}"
        )


@router.post("/publish", response_model=PublishResponse)
async def publish_content(
    request: PublishRequest,
    package_file: UploadFile = File(...),
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """
    發佈內容到配置的發佈服務

    這是一個中性的 HTTP 代理，不關心背後是 mindscape-ai-cloud 還是其他服務
    """
    config = get_publish_service_config(settings_store)
    if not config:
        raise HTTPException(
            status_code=400,
            detail="發佈服務未配置，請先配置發佈服務"
        )

    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail="發佈服務已禁用"
        )

    try:
        # 讀取上傳的文件
        file_content = await package_file.read()

        # 構建發佈服務的 API URL
        publish_url = f"{config.api_url.rstrip('/')}/api/v1/publish"

        # 準備請求體
        files = {
            'package_file': (package_file.filename, file_content, package_file.content_type or 'application/zip')
        }
        data = {
            'content_type': request.content_type,
            'content_id': request.content_id,
            'version': request.version
        }
        if request.options:
            # 將 options 作為 JSON 字符串傳遞，或根據發佈服務的 API 格式調整
            import json
            data['options'] = json.dumps(request.options)

        # 調用發佈服務 API
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
                    message=result_data.get("message", "發佈成功"),
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
                    detail=f"發佈服務錯誤：{error_msg}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="發佈服務響應超時"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to publish: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"發佈失敗：{str(e)}"
        )


@router.get("/history")
async def get_publish_history(
    limit: int = 50,
    offset: int = 0,
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """
    獲取發佈歷史（從配置的發佈服務查詢）
    """
    config = get_publish_service_config(settings_store)
    if not config:
        raise HTTPException(
            status_code=400,
            detail="發佈服務未配置"
        )

    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail="發佈服務已禁用"
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
                    detail=f"查詢發佈歷史失敗：{response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="發佈服務響應超時"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get publish history: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"查詢發佈歷史失敗：{str(e)}"
        )


@router.get("/publish/{publish_id}/status")
async def get_publish_status(
    publish_id: str,
    settings_store: SystemSettingsStore = Depends(get_settings_store)
):
    """
    查詢發佈狀態（從配置的發佈服務查詢）
    """
    config = get_publish_service_config(settings_store)
    if not config:
        raise HTTPException(
            status_code=400,
            detail="發佈服務未配置"
        )

    if not config.enabled:
        raise HTTPException(
            status_code=400,
            detail="發佈服務已禁用"
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
                    detail=f"查詢發佈狀態失敗：{response.text}"
                )

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="發佈服務響應超時"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get publish status: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"查詢發佈狀態失敗：{str(e)}"
        )

