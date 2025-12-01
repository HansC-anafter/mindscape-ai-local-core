"""
System Settings Models

Generic system settings model for storing various system-level configurations.
Supports key-value pairs with type safety and validation.
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Union, List
from enum import Enum
from datetime import datetime


class SettingType(str, Enum):
    """Setting value types"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    JSON = "json"
    ARRAY = "array"


class ModelType(str, Enum):
    """Model types for LLM configuration"""
    CHAT = "chat"
    EMBEDDING = "embedding"


class LLMModelConfig(BaseModel):
    """
    LLM Model Configuration

    Represents a single model configuration with provider and type information.
    """
    model_name: str = Field(..., description="Model name (e.g., 'gpt-4o-mini', 'text-embedding-3-small')")
    provider: str = Field(..., description="Provider name (e.g., 'openai', 'anthropic')")
    model_type: ModelType = Field(..., description="Model type: chat or embedding")
    api_key_setting_key: Optional[str] = Field(
        None,
        description="Key in system_settings for API key (e.g., 'openai_api_key')"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional model metadata (dimensions, max tokens, etc.)"
    )


class SystemSetting(BaseModel):
    """
    System Setting

    Generic key-value setting with type information and metadata.
    """
    key: str = Field(..., description="Setting key (unique identifier)")
    value: Union[str, int, float, bool, Dict[str, Any], List[Any]] = Field(
        ...,
        description="Setting value (type depends on value_type)"
    )
    value_type: SettingType = Field(
        ...,
        description="Type of the value"
    )
    category: str = Field(
        default="general",
        description="Setting category (e.g., 'llm', 'ui', 'security', 'general')"
    )
    description: Optional[str] = Field(
        None,
        description="Human-readable description of this setting"
    )
    is_sensitive: bool = Field(
        default=False,
        description="Whether this setting contains sensitive data (e.g., API keys)"
    )
    is_user_editable: bool = Field(
        default=True,
        description="Whether users can edit this setting via UI"
    )
    default_value: Optional[Union[str, int, float, bool, Dict[str, Any], List[Any]]] = Field(
        None,
        description="Default value for this setting"
    )
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (validation rules, constraints, etc.)"
    )
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Last update timestamp"
    )


class SystemSettingsUpdate(BaseModel):
    """Request to update system settings"""
    settings: Dict[str, Union[str, int, float, bool, Dict[str, Any], List[Any]]] = Field(
        ...,
        description="Dictionary of setting keys and values to update"
    )


class SystemSettingsResponse(BaseModel):
    """Response containing system settings"""
    settings: Dict[str, Any] = Field(
        ...,
        description="Dictionary of all settings (sensitive values may be masked)"
    )
    categories: List[str] = Field(
        ...,
        description="List of available setting categories"
    )


class LLMModelSettingsResponse(BaseModel):
    """Response containing LLM model configurations"""
    chat_model: Optional[LLMModelConfig] = Field(
        None,
        description="Chat/conversation model configuration"
    )
    embedding_model: Optional[LLMModelConfig] = Field(
        None,
        description="Embedding model configuration"
    )
    available_chat_models: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of available chat models"
    )
    available_embedding_models: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="List of available embedding models"
    )
