"""
Layer artifacts — typed inter-layer contracts for the meeting engine.

L1 → RoundVerdict:      structured convergence signal (replaces string marker)
L3 → DispatchManifest:  aggregated gate result with approved / clarify / deferred / blocked
"""

from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field

from backend.app.models.action_intent import ActionIntent


class RoundVerdict(BaseModel):
    """L1 convergence signal emitted by the facilitator.

    Replaces the fragile ``[converged]`` string marker with a typed
    contract so downstream layers can inspect convergence reason and
    remaining concerns without text parsing.
    """

    converged: bool = Field(..., description="Whether the meeting round has converged")
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Convergence confidence (0.0–1.0)",
    )
    reason: str = Field(default="", description="Human-readable convergence reason")
    remaining_concerns: List[str] = Field(
        default_factory=list,
        description="Open items that were not fully resolved",
    )
    coverage_pass: bool = Field(
        default=True,
        description="Whether CoverageMatrix audit passed (P1-C)",
    )
    risk_pass: bool = Field(
        default=True,
        description="Whether risk assessment passed",
    )
    decomposition_ready: bool = Field(
        default=False,
        description="Whether output is ready for decomposition",
    )
    next_action: str = Field(
        default="more_rounds",
        description="more_rounds | synthesize | abort",
    )

    @classmethod
    def from_text(cls, text: str) -> "RoundVerdict":
        """Fallback: parse legacy ``[converged]`` / ``[not converged]`` text.

        Used during migration when facilitator output is not yet JSON.
        """
        lower = text.strip().lower()
        converged = "[converged]" in lower and "[not converged]" not in lower
        return cls(
            converged=converged,
            confidence=0.8 if converged else 0.3,
            reason="text_marker_fallback",
        )

    @classmethod
    def try_parse(cls, text: str) -> "RoundVerdict":
        """Attempt JSON parse → fall back to text marker.

        This is the primary entry point for convergence checking.
        """
        import json

        stripped = text.strip()

        # Try to find JSON object in the text
        for start_char, end_char in [
            ("{", "}"),
        ]:
            start = stripped.find(start_char)
            end = stripped.rfind(end_char)
            if start != -1 and end > start:
                candidate = stripped[start : end + 1]
                try:
                    data = json.loads(candidate)
                    if "converged" in data:
                        return cls.model_validate(data)
                except (json.JSONDecodeError, Exception):
                    pass

        # Fallback to text marker
        return cls.from_text(stripped)


class DispatchManifest(BaseModel):
    """L3 dispatch gate aggregated result.

    Collects gate decisions into typed buckets.  The ``blocked`` list
    aggregates items with ``landing_status='policy_blocked'`` from the
    upstream policy gate — it is NOT a new ``GateDecision``.
    """

    approved: List[ActionIntent] = Field(
        default_factory=list,
        description="Intents approved for dispatch (GateDecision.DISPATCH_NOW)",
    )
    clarify: List["IntentDecision"] = Field(
        default_factory=list,
        description="Intents needing clarification (GateDecision.CLARIFY)",
    )
    deferred: List["IntentDecision"] = Field(
        default_factory=list,
        description="Intents deferred (GateDecision.DEFER or SHRINK_SCOPE)",
    )
    blocked: List[ActionIntent] = Field(
        default_factory=list,
        description="Policy-gate blocked intents (aggregated view, not a gate decision)",
    )

    @classmethod
    def from_gate_result(
        cls,
        gate_result: "GateResult",
        intents: List[ActionIntent],
        blocked_intents: Optional[List[ActionIntent]] = None,
    ) -> "DispatchManifest":
        """Build manifest from DispatchGate result + optional policy-blocked intents."""
        intent_map = {i.intent_id: i for i in intents}

        approved = [
            intent_map[iid] for iid in gate_result.dispatch_intents if iid in intent_map
        ]

        return cls(
            approved=approved,
            clarify=gate_result.clarify_intents,
            deferred=gate_result.deferred_intents,
            blocked=blocked_intents or [],
        )


# Avoid circular import — these are only used for type annotations
# and at runtime by from_gate_result() which receives already-constructed objects.
from backend.app.services.orchestration.meeting.dispatch_gate import (  # noqa: E402
    GateResult,
    IntentDecision,
)
