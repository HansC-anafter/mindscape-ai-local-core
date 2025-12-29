"""
Evidence models for Mind-Lens observability.

Evidence tracks how lens nodes are triggered during execution.
"""
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime, timezone


class Evidence(BaseModel):
    """Node trigger evidence"""
    node_id: str
    node_label: str
    snapshot_id: str
    execution_id: str
    workspace_id: str
    workspace_name: Optional[str] = None
    output_snippet: str = Field(description="Output snippet proving node influence")
    triggered_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class DriftReport(BaseModel):
    """Lens drift report"""
    profile_id: str
    days: int
    total_executions: int
    node_drift: List[dict] = Field(default_factory=list, description="Node usage drift data")
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}

