"""Governed world-memory packet surfaced to downstream readers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class WorldMemoryPacket:
    """Bounded packet exported from the world-memory state plane."""

    workspace_id: str
    profile_id: str
    governance_context: Dict[str, Any] = field(default_factory=dict)
    active_schedule: Optional[Dict[str, Any]] = None
    schedule_artifact_refs: List[Dict[str, Any]] = field(default_factory=list)
    schedule_constraints: Dict[str, Any] = field(default_factory=dict)
    performance_state: Optional[Dict[str, Any]] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

