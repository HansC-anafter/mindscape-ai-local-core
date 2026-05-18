from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

class IntentResponse(BaseModel):
    """Intent API response model matching the API draft specification"""

    id: str
    workspace_id: str
    title: str
    description: Optional[str] = None
    status: str  # 'CANDIDATE' | 'CONFIRMED' | 'REJECTED'
    parent_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: str
    updated_at: str

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})


class IntentTreeNode(IntentResponse):
    """Intent tree node with children"""

    children: Optional[List["IntentTreeNode"]] = None


class CreateIntentRequest(BaseModel):
    """Request model for creating a new intent"""

    workspace_id: str
    title: str
    description: Optional[str] = None
    status: Optional[str] = "CONFIRMED"  # Default to CONFIRMED
    parent_id: Optional[str] = None
    storyline_tags: Optional[List[str]] = Field(
        default_factory=list,
        description="Storyline tags for cross-project story tracking",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class UpdateIntentRequest(BaseModel):
    """Request model for updating an intent"""

    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    parent_id: Optional[str] = None
    storyline_tags: Optional[List[str]] = Field(
        None, description="Storyline tags for cross-project story tracking"
    )
    metadata: Optional[Dict[str, Any]] = None


class ListIntentsResponse(BaseModel):
    """Response model for listing intents"""

    intents: List[IntentResponse]


class ListIntentsTreeResponse(BaseModel):
    """Response model for listing intents as a tree"""

    intents: List[IntentTreeNode]


# ============================================================================
# Helper Functions
