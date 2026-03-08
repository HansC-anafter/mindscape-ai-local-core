"""
ActionIntent — Typed executor output for L2-Online normalization.

Each ActionIntent represents a single action extracted from executor
output.  The SemanticNormalizer produces ``ActionIntent[]`` from raw
JSON/text, and the IR compiler consumes them to build TaskIR phases.
"""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class IntentConfidence(str, Enum):
    """Confidence in the parsed intent."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ActionIntent(BaseModel):
    """
    Typed representation of a single action from executor output.

    One ActionIntent maps to one PhaseIR in the compiled TaskIR.
    The ``intent_id`` is stable across recompilation (INV-1).
    """

    intent_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Stable intent ID (INV-1: survives recompilation)",
    )
    title: str = Field(
        ...,
        description="Human-readable action title",
    )
    description: str = Field(
        default="",
        description="Detailed description of the action",
    )
    assignee: str = Field(
        default="",
        description="Who should execute this (workspace, agent, user)",
    )
    confidence: IntentConfidence = Field(
        default=IntentConfidence.HIGH,
        description="Parsing confidence",
    )

    # Actuator binding
    tool_name: Optional[str] = Field(
        default=None,
        description="Resolved tool name (from RAG or explicit)",
    )
    playbook_code: Optional[str] = Field(
        default=None,
        description="Resolved playbook code",
    )
    input_params: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Input parameters for tool/playbook",
    )

    # Routing
    target_workspace_id: Optional[str] = Field(
        default=None,
        description="Target workspace for cross-workspace dispatch",
    )
    depends_on: Optional[List[str]] = Field(
        default=None,
        description="Intent IDs this action depends on (passthrough, INV-4)",
    )

    # Priority / metadata
    priority: Optional[str] = Field(
        default=None,
        description="Priority: high | medium | low",
    )
    engine: Optional[str] = Field(
        default=None,
        description="Preferred execution engine (e.g. playbook:generic)",
    )
    asset_refs: List[str] = Field(
        default_factory=list,
        description="Referenced asset IDs",
    )

    # Policy gate results (populated post-normalization)
    landing_status: Optional[str] = Field(
        default=None,
        description="Dispatch status: launched | task_created | policy_blocked | ...",
    )
    policy_reason_code: Optional[str] = Field(
        default=None,
        description="Reason code if policy-blocked",
    )

    def to_action_item_dict(self) -> Dict[str, Any]:
        """Convert to legacy action_item dict for backward compat."""
        d: Dict[str, Any] = {
            "title": self.title,
            "description": self.description,
            "assignee": self.assignee,
            "tool_name": self.tool_name,
            "playbook_code": self.playbook_code,
            "input_params": self.input_params,
            "target_workspace_id": self.target_workspace_id,
            "priority": self.priority,
            "engine": self.engine,
            "asset_refs": self.asset_refs,
            "intent_id": self.intent_id,
        }
        if self.depends_on:
            d["blocked_by"] = self.depends_on
        if self.landing_status:
            d["landing_status"] = self.landing_status
        if self.policy_reason_code:
            d["policy_reason_code"] = self.policy_reason_code
        return d

    @classmethod
    def from_action_item_dict(cls, d: Dict[str, Any]) -> "ActionIntent":
        """Create from legacy action_item dict."""
        return cls(
            intent_id=d.get("intent_id", str(uuid.uuid4())),
            title=d.get("title") or d.get("action") or "Untitled",
            description=d.get("description") or d.get("detail") or "",
            assignee=d.get("assignee") or d.get("owner") or "",
            tool_name=d.get("tool_name"),
            playbook_code=d.get("playbook_code"),
            input_params=d.get("input_params"),
            target_workspace_id=d.get("target_workspace_id"),
            depends_on=d.get("blocked_by"),
            priority=d.get("priority"),
            engine=d.get("engine"),
            asset_refs=d.get("asset_refs") or [],
        )
