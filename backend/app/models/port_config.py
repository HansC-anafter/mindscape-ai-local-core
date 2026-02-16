"""
Port Configuration Models

Configuration models for ports, hostnames, and service URLs.
"""

from typing import Dict, Optional, List
from pydantic import BaseModel, Field, validator


class PortConfig(BaseModel):
    """Port configuration model."""

    backend_api: int = Field(
        default=8200, ge=1024, le=65535, description="Backend API port"
    )
    frontend: int = Field(
        default=8300, ge=1024, le=65535, description="Frontend Web Console port"
    )
    ocr_service: int = Field(
        default=8400, ge=1024, le=65535, description="OCR service port"
    )
    postgres: int = Field(
        default=5440, ge=1024, le=65535, description="PostgreSQL port"
    )
    cloud_api: Optional[int] = Field(
        default=None, ge=1024, le=65535, description="Cloud API port (optional)"
    )
    cloud_provider_api: Optional[int] = Field(
        default=8102, ge=1024, le=65535, description="Cloud provider API port"
    )

    # Cluster and environment scoping
    cluster: Optional[str] = Field(
        default=None, description="Cluster identifier (e.g. prod-cluster-1)"
    )
    environment: Optional[str] = Field(
        default=None,
        description="Environment identifier (e.g. production, staging, development)",
    )
    site: Optional[str] = Field(
        default=None, description="Site identifier (e.g. site-1)"
    )

    @validator(
        "backend_api",
        "frontend",
        "ocr_service",
        "postgres",
        "cloud_api",
        "cloud_provider_api",
        pre=True,
    )
    def validate_port(cls, v):
        if v is None:
            return v
        if not isinstance(v, int):
            try:
                v = int(v)
            except (ValueError, TypeError):
                raise ValueError(f"Port must be an integer: {v}")
        if not (1024 <= v <= 65535):
            raise ValueError(f"Port must be in range 1024-65535: {v}")
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "backend_api": 8200,
                "frontend": 8300,
                "ocr_service": 8400,
                "postgres": 5440,
                "cloud_api": 8500,
                "cloud_provider_api": 8102,
                "cluster": "prod-cluster-1",
                "environment": "production",
                "site": "site-1",
            }
        }


class HostConfig(BaseModel):
    """Hostname configuration model."""

    backend_api_host: str = Field(
        default="localhost", description="Backend API hostname"
    )
    frontend_host: str = Field(default="localhost", description="Frontend hostname")
    ocr_service_host: str = Field(
        default="localhost", description="OCR service hostname"
    )
    cloud_api_host: Optional[str] = Field(
        default=None, description="Cloud API hostname"
    )
    cloud_provider_api_host: Optional[str] = Field(
        default="localhost", description="Cloud provider API hostname"
    )

    # Allowed CORS origins
    cors_origins: List[str] = Field(
        default_factory=list, description="List of allowed CORS origins"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "backend_api_host": "localhost",
                "frontend_host": "localhost",
                "ocr_service_host": "localhost",
                "cloud_api_host": "api.example.com",
                "cloud_provider_api_host": "localhost",
                "cors_origins": ["http://localhost:8300", "https://app.example.com"],
            }
        }


class ServiceURLConfig(BaseModel):
    """Service URL configuration model."""

    backend_api_url: str
    frontend_url: str
    ocr_service_url: str
    cloud_api_url: Optional[str] = None
    cloud_provider_api_url: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "backend_api_url": "http://localhost:8200",
                "frontend_url": "http://localhost:8300",
                "ocr_service_url": "http://localhost:8400",
                "cloud_api_url": "https://api.example.com:8500",
                "cloud_provider_api_url": "http://localhost:8102",
            }
        }
