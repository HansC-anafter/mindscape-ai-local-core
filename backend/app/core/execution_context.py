"""
Execution Context - Core domain abstraction for execution context
"""

from typing import Dict, Optional
from pydantic import BaseModel


class ExecutionContext(BaseModel):
    """
    Execution context - Core domain abstraction

    Attributes:
        actor_id: Actor ID
        workspace_id: Workspace ID
        tags: Optional key-value dictionary for additional context
    """
    actor_id: str
    workspace_id: str
    tags: Optional[Dict[str, str]] = None

    class Config:
        json_encoders = {
            dict: lambda v: v
        }

