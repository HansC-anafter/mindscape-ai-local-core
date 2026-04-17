"""Rendered world-card projection emitted from governed world memory."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class WorldCardProjection:
    """Text-oriented world-card summary for prompt/context injection."""

    title: str = "World Card"
    summary_lines: List[str] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    suggested_focus: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

