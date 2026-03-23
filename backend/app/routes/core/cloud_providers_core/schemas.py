"""Pydantic schemas for cloud provider routes."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ProviderConfig(BaseModel):
    """Provider configuration model."""

    provider_id: str = Field(..., description="Unique provider identifier")
    provider_type: str = Field(
        ...,
        description="Provider type: official, generic_http, or custom",
    )
    enabled: bool = Field(True, description="Whether provider is enabled")
    config: Dict[str, Any] = Field(
        ...,
        description="Provider-specific configuration",
    )


class ProviderResponse(BaseModel):
    """Provider response model."""

    provider_id: str
    provider_type: str
    enabled: bool
    configured: bool
    name: str
    description: str
    config: Dict[str, Any]


class ProviderAction(BaseModel):
    """Provider action link."""

    type: str
    label: str
    rel: str
    url: str
    expires_at: Optional[str] = None


class ProviderActionRequired(BaseModel):
    """Provider action-required response."""

    state: str
    reason: str
    actions: List[ProviderAction]
    retry_after_sec: Optional[int] = None


class TestConnectionResponse(BaseModel):
    """Connection test response model."""

    success: bool
    message: str
    action_required: Optional[ProviderActionRequired] = None
