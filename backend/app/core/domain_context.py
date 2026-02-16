"""
Local Domain Context - Core domain abstraction for local workspace context

WARNING: This is a LOCAL DOMAIN MODEL, not the execution protocol.
It represents workspace/actor/mind-lens state for UI/governance layer.

Hard Rule: local-core core does NOT depend on cloud-execution-protocol.
Protocol package is only installed in pack runtime venv (via Pack Installer).

Hard Rule: local-core core does NOT directly call cloud provider API.
For cloud handoff/communication, must use external tools (not in local-core repo).
"""

from typing import Dict, Optional, Any
from pydantic import BaseModel


class LocalDomainContext(BaseModel):
    """
    Local domain context - Core domain abstraction for local workspace

    This is the domain model for local-core's workspace/actor/mind-lens state.
    It is NOT the execution protocol context used by portable tools.

    Attributes:
        actor_id: Actor ID
        workspace_id: Workspace ID
        tags: Optional key-value dictionary for additional context
            - Can include: policy_set_id, assets_refs, lens_stack (as metadata)
        mind_lens: Optional resolved Mind Lens for role-based perspective
    """

    actor_id: str
    workspace_id: str
    tags: Optional[Dict[str, Any]] = None
    mind_lens: Optional[Dict[str, Any]] = None

    class Config:
        json_encoders = {dict: lambda v: v}

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "actor_id": self.actor_id,
            "workspace_id": self.workspace_id,
            "tags": self.tags or {},
            "mind_lens": self.mind_lens,
        }
