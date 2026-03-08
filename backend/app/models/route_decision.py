"""
RouteDecision — Sole ingress routing contract (ADR-R1).

Every ingress request (chat, handoff-bundle compile, API intake) must
produce exactly one RouteDecision.  Downstream consumers branch on
route_kind + execution_profile, never on raw flags like
``meeting_enabled`` or ``executor_runtime``.

Vocabulary:
    route_kind      – which primary path (fast|governed|meeting)
    execution_profile – runtime profile (simple|durable), orthogonal axis
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────


class RouteKind(str, Enum):
    """Primary routing path — which pipeline branch to enter."""

    FAST = "fast"  # Direct LLM response, no governance overhead
    GOVERNED = "governed"  # Agent-dispatched execution with governance
    MEETING = "meeting"  # Full meeting engine (L1–L5 pipeline)


class ExecutionProfileKind(str, Enum):
    """
    Runtime execution profile — orthogonal to route_kind.

    A meeting can be ``simple``; a governed task can be ``durable``.
    """

    SIMPLE = "simple"
    DURABLE = "durable"


class RouteReasonCode(str, Enum):
    """Canonical reason codes explaining why a route was chosen."""

    # route_kind selection
    EXECUTION_MODE_QA = "execution_mode_qa"
    EXECUTION_MODE_EXECUTION = "execution_mode_execution"
    EXECUTION_MODE_HYBRID = "execution_mode_hybrid"
    EXECUTION_MODE_MEETING = "execution_mode_meeting"
    PROJECT_MEETING_ENABLED = "project_meeting_enabled"
    EXECUTOR_RUNTIME_PRESENT = "executor_runtime_present"
    NO_EXECUTOR_RUNTIME = "no_executor_runtime"
    HANDOFF_BUNDLE_COMPILE = "handoff_bundle_compile"

    # execution_profile selection
    PROFILE_SIMPLE_DEFAULT = "profile_simple_default"
    PROFILE_DURABLE_REQUESTED = "profile_durable_requested"

    # compatibility / fallback
    LEGACY_PATH_COMPAT = "legacy_path_compat"
    FEATURE_FLAG_OFF = "feature_flag_off"


class TransitionKind(str, Enum):
    """Explicit path promotion types."""

    FAST_TO_GOVERNED = "fast_to_governed"
    FAST_TO_MEETING = "fast_to_meeting"
    GOVERNED_TO_MEETING = "governed_to_meeting"
    MEETING_TO_GOVERNED = "meeting_to_governed"
    POST_RESPONSE_PLAYBOOK = "post_response_playbook"


# ─────────────────────────────────────────────────────
# Core models
# ─────────────────────────────────────────────────────


class RouteDecision(BaseModel):
    """
    Immutable routing decision produced by IngressRouter.

    One instance per ingress request.  Downstream code must not
    re-derive path decisions; it must inspect this object instead.
    """

    decision_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique decision ID",
    )
    route_kind: RouteKind = Field(
        ...,
        description="Primary path: fast | governed | meeting",
    )
    execution_profile: ExecutionProfileKind = Field(
        default=ExecutionProfileKind.SIMPLE,
        description="Runtime profile: simple | durable (orthogonal to route_kind)",
    )
    reason_codes: List[RouteReasonCode] = Field(
        default_factory=list,
        description="Why this path was chosen",
    )
    escalation_allowed: bool = Field(
        default=True,
        description="Whether this request can be upgraded to a higher path later",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    # Passthrough context — carried for downstream but NOT used for routing
    source_execution_mode: Optional[str] = Field(
        default=None,
        description="Original execution_mode from the request (qa|execution|hybrid|meeting)",
    )
    source_entry_point: Optional[str] = Field(
        default=None,
        description="Which entry point produced this decision (chat|compile|api)",
    )


class RouteTransition(BaseModel):
    """
    Explicit record of a path promotion after initial RouteDecision.

    Replaces hidden post-response upgrades.  Every transition is
    persisted and observable.
    """

    transition_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
    )
    decision_id: str = Field(
        ...,
        description="Parent RouteDecision this transition extends",
    )
    transition_kind: TransitionKind = Field(
        ...,
        description="What kind of promotion occurred",
    )
    reason: str = Field(
        default="",
        description="Human-readable explanation",
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
