"""Types shared by ToolEmbeddingService helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, TypedDict


@dataclass
class ToolMatch:
    """A tool matched by embedding similarity search."""

    tool_id: str
    display_name: str
    description: str
    category: str
    capability_code: Optional[str]
    similarity: float


class IndexableEntry(TypedDict):
    """Shared tool or playbook payload used during indexing."""

    tool_id: str
    display_name: str
    description: str
    category: str
    capability_code: Optional[str]
    affordance: Optional[dict[str, Any]]
