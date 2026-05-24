"""Service endpoint registry models."""

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class EndpointAudience(str, Enum):
    """Endpoint audience classes used by local-core and capability packs."""

    BROWSER_PUBLIC = "browser_public"
    HOST_PUBLIC = "host_public"
    CONTAINER_INTERNAL = "container_internal"
    SERVER_INTERNAL = "server_internal"


class ServiceEndpoint(BaseModel):
    """Single service endpoint for a specific audience."""

    service_id: str = Field(..., description="Stable service endpoint id")
    audience: EndpointAudience = Field(..., description="Target endpoint audience")
    url: str = Field(..., description="Endpoint URL or same-origin relative base")
    source: str = Field(default="seed", description="Resolution source")
    label: Optional[str] = Field(default=None, description="Display label")
    description: Optional[str] = Field(default=None, description="Display description")
    is_user_editable: bool = Field(
        default=True,
        description="Whether users can override this endpoint through settings",
    )

    model_config = ConfigDict(use_enum_values=True)


class ServiceEndpointSnapshot(BaseModel):
    """Versioned endpoint registry snapshot."""

    version: int = Field(default=1)
    endpoints: List[ServiceEndpoint] = Field(default_factory=list)

    model_config = ConfigDict(use_enum_values=True)


class ServiceEndpointURLResponse(BaseModel):
    """Resolved service endpoint URL response."""

    service_id: str
    audience: EndpointAudience
    url: str
    source: str = "seed"

    model_config = ConfigDict(use_enum_values=True)


class ServiceEndpointUpdate(BaseModel):
    """Request payload for overriding a service endpoint URL."""

    url: str


class RuntimeServiceEndpointSnapshot(BaseModel):
    """JSON-safe runtime context endpoint snapshot."""

    version: int = 1
    endpoints: List[Dict[str, str]] = Field(default_factory=list)
