"""
Configuration models for user settings

Design Principles:
- Platform-neutral: Not bound to any specific service
- Multi-backend support: Can configure multiple remote backends
- Backward compatible: Supports legacy configuration formats
"""

from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List


class RemoteBackendConfig(BaseModel):
    """
    Remote Backend Configuration

    Purpose: Describes how to connect to remote agent services
    Supports: Console-Kit CRS-Hub, LangGraph Cloud, self-hosted services
    """

    name: str = Field(
        ...,
        description="Backend name (unique identifier)"
    )

    base_url: str = Field(
        ...,
        description="Remote service URL (platform-neutral)"
    )

    api_token: str = Field(
        ...,
        description="API Token (for authentication)"
    )

    endpoint: str = Field(
        default="/api/run_simple",
        description="Execution endpoint (default: /api/run_simple)"
    )

    protocol: str = Field(
        default="generic",
        description="Protocol type: generic | openai-like | langchain-like"
    )

    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata (e.g., source, creation time, etc.)"
    )


class AgentBackendConfig(BaseModel):
    """
    Agent Backend Configuration

    Design Principles:
    - Not bound to any specific platform
    - Supports multiple remote backends
    - Backward compatible with legacy configurations
    """

    # Currently enabled backend type
    mode: str = Field(
        default="local",
        description="Enabled backend: local | http_remote | custom"
    )

    # Local LLM configuration
    openai_api_key: Optional[str] = Field(
        None,
        description="OpenAI API Key (for local mode)"
    )

    anthropic_api_key: Optional[str] = Field(
        None,
        description="Anthropic API Key (for local mode)"
    )

    vertex_api_key: Optional[str] = Field(
        None,
        description="Google Vertex AI API Key or Service Account JSON (for local mode)"
    )

    vertex_project_id: Optional[str] = Field(
        None,
        description="Google Cloud Project ID for Vertex AI"
    )

    vertex_location: Optional[str] = Field(
        None,
        description="Vertex AI location (e.g., us-central1, asia-east1)"
    )

    # Remote backend configurations (can have multiple)
    remote_backends: List[RemoteBackendConfig] = Field(
        default_factory=list,
        description="Remote backend configuration list (can configure multiple)"
    )

    # Currently selected remote backend (if mode='http_remote')
    active_remote_backend: Optional[str] = Field(
        None,
        description="Currently used remote backend name"
    )

    # Backward compatibility fields (deprecated but retained for legacy config support)
    remote_crs_url: Optional[str] = Field(
        None,
        description="[Deprecated] Remote CRS URL (backward compatibility)",
        deprecated=True
    )

    remote_crs_token: Optional[str] = Field(
        None,
        description="[Deprecated] Remote CRS Token (backward compatibility)",
        deprecated=True
    )


class IntentConfig(BaseModel):
    """Intent analysis configuration"""
    use_llm: bool = Field(
        default=True,
        description="Enable LLM-based intent matching (if False, use rule-based only)"
    )
    rule_priority: bool = Field(
        default=True,
        description="If True, try rule-based matching first, then LLM. If False, try LLM first."
    )


class UserConfig(BaseModel):
    """User configuration settings"""
    profile_id: str
    agent_backend: AgentBackendConfig = Field(default_factory=AgentBackendConfig)
    intent_config: IntentConfig = Field(default_factory=IntentConfig)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateBackendConfigRequest(BaseModel):
    """更新 Backend 配置请求"""
    mode: str = Field(
        ...,
        description="Backend 模式：local | http_remote"
    )

    # Local mode configuration
    openai_api_key: Optional[str] = None
    anthropic_api_key: Optional[str] = None
    vertex_api_key: Optional[str] = None
    vertex_project_id: Optional[str] = None
    vertex_location: Optional[str] = None

    # Remote mode configuration (backward compatible)
    remote_crs_url: Optional[str] = None
    remote_crs_token: Optional[str] = None


class AddRemoteBackendRequest(BaseModel):
    """添加远端 Backend 请求"""
    config: RemoteBackendConfig


class SetActiveBackendRequest(BaseModel):
    """设置当前 Backend 请求"""
    backend_type: str = Field(
        ...,
        description="Backend 类型：local | http_remote"
    )

    backend_name: Optional[str] = Field(
        None,
        description="Backend 名称（用于 http_remote）"
    )
