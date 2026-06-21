"""Tool slot prompt data types."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

from backend.app.models.playbook import ToolPolicy


@dataclass
class ToolSlotInfo:
    """Tool slot information for prompt injection."""

    slot: str
    description: Optional[str] = None
    policy: Optional[ToolPolicy] = None
    mapped_tool_id: Optional[str] = None
    mapped_tool_description: Optional[str] = None
    source: str = "unknown"
    relevance_score: Optional[float] = None
    tags: Optional[List[str]] = None
    priority: int = 0
