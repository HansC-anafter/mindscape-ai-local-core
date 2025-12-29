"""
端口配置模型

提供端口、主机名和服务 URL 的配置模型
"""
from typing import Dict, Optional, List
from pydantic import BaseModel, Field, validator


class PortConfig(BaseModel):
    """端口配置模型"""
    backend_api: int = Field(default=8200, ge=1024, le=65535, description="后端 API 端口")
    frontend: int = Field(default=8300, ge=1024, le=65535, description="前端 Web Console 端口")
    ocr_service: int = Field(default=8400, ge=1024, le=65535, description="OCR 服务端口")
    postgres: int = Field(default=5440, ge=1024, le=65535, description="PostgreSQL 端口")
    cloud_api: Optional[int] = Field(default=None, ge=1024, le=65535, description="Cloud API 端口（可选）")
    site_hub_api: Optional[int] = Field(default=8102, ge=1024, le=65535, description="Site-Hub API 端口")

    # 集群和环境作用域
    cluster: Optional[str] = Field(default=None, description="集群标识（如：prod-cluster-1）")
    environment: Optional[str] = Field(default=None, description="环境标识（如：production, staging, development）")
    site: Optional[str] = Field(default=None, description="站点标识（如：site-1）")

    @validator('backend_api', 'frontend', 'ocr_service', 'postgres', 'cloud_api', 'site_hub_api', pre=True)
    def validate_port(cls, v):
        if v is None:
            return v
        if not isinstance(v, int):
            try:
                v = int(v)
            except (ValueError, TypeError):
                raise ValueError(f"端口必须是整数: {v}")
        if not (1024 <= v <= 65535):
            raise ValueError(f"端口必须在 1024-65535 范围内: {v}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "backend_api": 8200,
                "frontend": 8300,
                "ocr_service": 8400,
                "postgres": 5440,
                "cloud_api": 8500,
                "site_hub_api": 8102,
                "cluster": "prod-cluster-1",
                "environment": "production",
                "site": "site-1"
            }
        }


class HostConfig(BaseModel):
    """主机名配置模型"""
    backend_api_host: str = Field(default="localhost", description="后端 API 主机名")
    frontend_host: str = Field(default="localhost", description="前端主机名")
    ocr_service_host: str = Field(default="localhost", description="OCR 服务主机名")
    cloud_api_host: Optional[str] = Field(default=None, description="Cloud API 主机名")
    site_hub_api_host: Optional[str] = Field(default="localhost", description="Site-Hub API 主机名")

    # CORS 允许的源
    cors_origins: List[str] = Field(default_factory=list, description="CORS 允许的源列表")

    class Config:
        json_schema_extra = {
            "example": {
                "backend_api_host": "localhost",
                "frontend_host": "localhost",
                "ocr_service_host": "localhost",
                "cloud_api_host": "api.example.com",
                "site_hub_api_host": "localhost",
                "cors_origins": [
                    "http://localhost:8300",
                    "https://app.example.com"
                ]
            }
        }


class ServiceURLConfig(BaseModel):
    """服务 URL 配置模型"""
    backend_api_url: str
    frontend_url: str
    ocr_service_url: str
    cloud_api_url: Optional[str] = None
    site_hub_api_url: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "backend_api_url": "http://localhost:8200",
                "frontend_url": "http://localhost:8300",
                "ocr_service_url": "http://localhost:8400",
                "cloud_api_url": "https://api.example.com:8500",
                "site_hub_api_url": "http://localhost:8102"
            }
        }

