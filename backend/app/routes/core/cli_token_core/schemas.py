from typing import Any, Optional

from pydantic import BaseModel, Field


class RegisterHostSessionRuntimeRequest(BaseModel):
    workspace_id: str = Field(..., description="Workspace that owns this runtime")
    surface: str = Field(..., description="CLI surface, e.g. codex_cli")
    owner_user_id: Optional[str] = Field(
        default=None,
        description="Optional workspace owner hint to avoid reloading workspace state",
    )
    client_id: Optional[str] = Field(
        default=None,
        description="Connected bridge client id for traceability",
    )
    runtime_id: Optional[str] = Field(
        default=None,
        description="Optional explicit runtime id override",
    )
    runtime_name: Optional[str] = Field(
        default=None,
        description="Optional display name override",
    )
    pool_group: Optional[str] = Field(
        default=None,
        description="Optional pool group override",
    )
    pool_enabled: bool = Field(
        default=True,
        description="Whether this runtime participates in managed runtime selection",
    )
    pool_priority: int = Field(
        default=0,
        description="Lower values are selected earlier within a pool",
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Runtime metadata such as CODEX_HOME/HOME/XDG paths",
    )


class RegisterHostSessionRuntimeBatchRequest(BaseModel):
    runtimes: list[RegisterHostSessionRuntimeRequest] = Field(
        ...,
        min_length=1,
        max_length=256,
        description="One workspace-scoped batch of host-session runtimes",
    )
