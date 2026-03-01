"""API request/response models for playbook routes."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class CreatePlaybookRequest(BaseModel):
    """Request to create a new playbook."""

    playbook_code: str
    name: str
    description: str = ""
    tags: List[str] = Field(default_factory=list)
    sop_content: str = ""
    owner: Optional[Dict[str, Any]] = None


class UpdatePlaybookRequest(BaseModel):
    """Request to update a playbook."""

    name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[List[str]] = None
    sop_content: Optional[str] = None
    user_notes: Optional[str] = None
    playbook_json: Optional[Dict[str, Any]] = None


class PlaybookAssociation(BaseModel):
    """Association between IntentCard and Playbook."""

    intent_id: str
    playbook_code: str
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(json_encoders={datetime: lambda v: v.isoformat()})

