"""Shared composition graph model aliases and common payloads."""

from __future__ import annotations

from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CompositionGraphPortDirection = Literal["input", "output"]
CompositionGraphDiagnosticSeverity = Literal["error", "warning", "info"]
CompositionGraphCompileStatus = Literal["succeeded", "failed"]
CompositionGraphRunStatus = Literal[
    "pending",
    "running",
    "waiting",
    "succeeded",
    "failed",
    "canceled",
]
CompositionGraphRunNodeStatus = Literal[
    "pending",
    "running",
    "waiting",
    "succeeded",
    "failed",
    "skipped",
]


class CompositionGraphViewport(BaseModel):
    """Viewport state persisted with a graph draft."""

    model_config = ConfigDict(extra="forbid")

    x: float = 0
    y: float = 0
    zoom: float = 1


class CompositionGraphDiagnostic(BaseModel):
    """Validation or compile diagnostic tied to a graph, node, or edge."""

    model_config = ConfigDict(extra="forbid")

    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    severity: CompositionGraphDiagnosticSeverity = "error"
    node_id: Optional[str] = None
    edge_id: Optional[str] = None
    port_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


__all__ = [
    "CompositionGraphCompileStatus",
    "CompositionGraphDiagnostic",
    "CompositionGraphDiagnosticSeverity",
    "CompositionGraphPortDirection",
    "CompositionGraphRunNodeStatus",
    "CompositionGraphRunStatus",
    "CompositionGraphViewport",
]
