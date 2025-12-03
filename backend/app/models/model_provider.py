"""
Model Provider Models

Models for managing model providers and model configurations.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from datetime import datetime
from enum import Enum


class ModelType(str, Enum):
    """Model types"""
    CHAT = "chat"
    EMBEDDING = "embedding"


class ModelConfig(BaseModel):
    """Individual model configuration"""
    id: Optional[int] = Field(None, description="Model ID (database primary key)")
    model_name: str = Field(..., description="Model name (e.g., 'gpt-5.1-pro')")
    provider_name: str = Field(..., description="Provider name (e.g., 'openai', 'anthropic')")
    model_type: ModelType = Field(..., description="Model type: chat or embedding")
    display_name: str = Field(..., description="Display name for UI")
    description: str = Field(..., description="Model description")
    enabled: bool = Field(default=False, description="Whether the model is enabled")
    is_latest: bool = Field(default=False, description="Whether this is the latest model")
    is_recommended: bool = Field(default=False, description="Whether this model is recommended")
    is_deprecated: bool = Field(default=False, description="Whether this model is deprecated")
    deprecation_date: Optional[str] = Field(None, description="Deprecation date (YYYY-MM-DD)")
    dimensions: Optional[int] = Field(None, description="Dimensions (for embedding models)")
    context_window: Optional[int] = Field(None, description="Context window size (for chat models)")
    icon: Optional[str] = Field(None, description="Icon for UI display")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class ModelProviderConfig(BaseModel):
    """Model provider configuration"""
    id: Optional[int] = Field(None, description="Provider ID (database primary key)")
    provider_name: str = Field(..., description="Provider identifier (e.g., 'openai', 'anthropic')")
    api_key_setting_key: str = Field(..., description="Key in system_settings for API key (e.g., 'openai_api_key')")
    base_url: Optional[str] = Field(None, description="Base URL for API (optional, for custom endpoints)")
    enabled: bool = Field(default=True, description="Whether the provider is enabled")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    created_at: Optional[datetime] = Field(None, description="Creation timestamp")
    updated_at: Optional[datetime] = Field(None, description="Last update timestamp")


class ModelConfigCard(BaseModel):
    """Model configuration card data for UI"""
    model: ModelConfig = Field(..., description="Model configuration")
    api_key_configured: bool = Field(..., description="Whether API key is configured")
    base_url: Optional[str] = Field(None, description="Base URL (if applicable)")
    quota_info: Optional[Dict[str, Any]] = Field(None, description="Quota information (if available)")


class ModelListResponse(BaseModel):
    """Response containing list of models"""
    models: List[ModelConfig] = Field(..., description="List of models")
    total: int = Field(..., description="Total number of models")


class ModelEnableRequest(BaseModel):
    """Request to enable/disable a model"""
    enabled: bool = Field(..., description="Whether to enable the model")

