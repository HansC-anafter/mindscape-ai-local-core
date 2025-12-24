"""
Execution Context - Core domain abstraction for execution context

Note: The four-layer model (Task/Policy/Lens/Assets) is a conceptual mapping,
not a structural change. See EXECUTION_CONTEXT_FOUR_LAYER_MODEL.md for concept mapping.
Existing fields are preserved and used as-is.
"""
from typing import Dict, Optional, Any
from pydantic import BaseModel


class ExecutionContext(BaseModel):
    """
    Execution context - Core domain abstraction

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
        json_encoders = {
            dict: lambda v: v
        }

