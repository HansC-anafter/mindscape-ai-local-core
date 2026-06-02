from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class PackResponse(BaseModel):
    """Response model for pack information"""

    id: str
    name: str
    description: str
    enabled_by_default: bool = False
    enabled: bool = False
    installed: bool = False
    routes: List[str] = []
    playbooks: List[str] = []
    tools: List[str] = []
    version: Optional[str] = None
    installed_at: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    restart_decision: Optional[Dict[str, Any]] = None
    backend_process_restart_required: Optional[bool] = None
    runner_restart_required: Optional[bool] = None
    activation: Optional["PackActivationStateResponse"] = None
    validation: Optional[Dict[str, Any]] = None


class PackActivationStateResponse(BaseModel):
    pack_id: str
    pack_family: str
    enabled: bool
    install_state: str
    migration_state: str
    activation_state: str
    activation_mode: str
    embedding_state: str = "unknown"
    embedding_error: Optional[str] = None
    embeddings_updated_at: Optional[str] = None
    manifest_hash: Optional[str] = None
    registered_prefixes: List[str] = Field(default_factory=list)
    last_error: Optional[str] = None
    activated_at: Optional[str] = None
    updated_at: Optional[str] = None
    restart_decision: Optional[Dict[str, Any]] = None
    backend_process_restart_required: Optional[bool] = None
    runner_restart_required: Optional[bool] = None


try:
    PackResponse.model_rebuild()
except AttributeError:
    PackResponse.update_forward_refs(
        PackActivationStateResponse=PackActivationStateResponse
    )
