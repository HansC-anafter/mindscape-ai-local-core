"""Meeting graph response models."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MeetingExecutionGraphNode(BaseModel):
    id: str
    title: str
    eyebrow: str
    detail: str = ""
    status: str = "ready"
    kind: str
    lane: str
    output: Optional[str] = None
    childCount: Optional[int] = None
    defaultInspector: Optional[str] = None
    traceFilter: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    degraded: bool = False


class MeetingExecutionGraphEdge(BaseModel):
    id: str
    from_id: str
    to_id: str
    type: str
    label: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class MeetingExecutionGraphResponse(BaseModel):
    workspace_id: str
    meeting_id: str
    nodes: List[MeetingExecutionGraphNode] = Field(default_factory=list)
    edges: List[MeetingExecutionGraphEdge] = Field(default_factory=list)
    lanes: List[str] = Field(
        default_factory=lambda: [
            "context",
            "commands",
            "runs",
            "outputs",
            "artifacts",
            "next",
        ]
    )
    task_count: int = 0
    relation_count: int = 0
    artifact_count: int = 0
    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
