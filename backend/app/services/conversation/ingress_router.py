"""
IngressRouter — Sole routing decision point (ADR-R1).

All entry points (chat, handoff-bundle compile, future API intake)
must call ``IngressRouter.decide()`` to produce a ``RouteDecision``
before any execution logic runs.

The router is **decision-only** — it never executes tasks, calls LLMs,
or interacts with transport.  This keeps the blast radius small.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from backend.app.models.route_decision import (
    ExecutionProfileKind,
    RouteDecision,
    RouteKind,
    RouteReasonCode,
    RouteTransition,
    TransitionKind,
)

logger = logging.getLogger(__name__)


class IngressRouter:
    """
    Stateless router that maps ingress signals to a RouteDecision.

    Usage::

        router = IngressRouter()
        decision = await router.decide(
            execution_mode="meeting",
            meeting_enabled=True,
            executor_runtime="gemini_cli",
            entry_point="chat",
        )

    The decision object is then consumed by PipelineCore, handoff-bundle
    compile, or any other entry point.
    """

    async def decide(
        self,
        *,
        execution_mode: str = "qa",
        meeting_enabled: bool = False,
        executor_runtime: Optional[str] = None,
        entry_point: str = "chat",
        store: Optional[Any] = None,
        project_id: Optional[str] = None,
    ) -> RouteDecision:
        """
        Produce a RouteDecision from ingress signals.

        Args:
            execution_mode: User-facing mode (qa|execution|hybrid|meeting).
            meeting_enabled: Whether meeting is enabled on the project.
            executor_runtime: Resolved executor runtime name (e.g. gemini_cli).
            entry_point: Which entry point is calling (chat|compile|api).
            store: MindscapeStore — needed to check project meeting flag.
            project_id: Project ID — used with store to check meeting flag.

        Returns:
            RouteDecision with route_kind, execution_profile, and reason_codes.
        """
        reasons: list[RouteReasonCode] = []

        # ── Step 1: Resolve meeting_enabled if store + project_id provided ──
        if not meeting_enabled and store and project_id:
            meeting_enabled = await self._check_project_meeting(project_id, store)
            if meeting_enabled:
                reasons.append(RouteReasonCode.PROJECT_MEETING_ENABLED)

        # ── Step 2: Determine route_kind ────────────────────────────────────
        if entry_point == "compile":
            # Handoff-bundle compile always routes to meeting
            route_kind = RouteKind.MEETING
            reasons.append(RouteReasonCode.HANDOFF_BUNDLE_COMPILE)
        elif execution_mode == "meeting" or meeting_enabled:
            route_kind = RouteKind.MEETING
            if execution_mode == "meeting":
                reasons.append(RouteReasonCode.EXECUTION_MODE_MEETING)
        elif executor_runtime:
            route_kind = RouteKind.GOVERNED
            reasons.append(RouteReasonCode.EXECUTOR_RUNTIME_PRESENT)
            # Track original mode
            reasons.append(self._mode_to_reason(execution_mode))
        else:
            route_kind = RouteKind.FAST
            reasons.append(RouteReasonCode.NO_EXECUTOR_RUNTIME)
            reasons.append(self._mode_to_reason(execution_mode))

        # ── Step 3: Determine execution_profile ─────────────────────────────
        # For now, default to SIMPLE.  Durable is selected when the
        # UnifiedDecisionCoordinator explicitly requests it (Phase 1+).
        execution_profile = ExecutionProfileKind.SIMPLE
        reasons.append(RouteReasonCode.PROFILE_SIMPLE_DEFAULT)

        # ── Step 4: Build decision ──────────────────────────────────────────
        decision = RouteDecision(
            route_kind=route_kind,
            execution_profile=execution_profile,
            reason_codes=reasons,
            escalation_allowed=(route_kind != RouteKind.MEETING),
            source_execution_mode=execution_mode,
            source_entry_point=entry_point,
        )

        logger.info(
            "[IngressRouter] decision_id=%s route=%s profile=%s reasons=%s entry=%s",
            decision.decision_id,
            decision.route_kind.value,
            decision.execution_profile.value,
            [r.value for r in decision.reason_codes],
            entry_point,
        )

        return decision

    def record_transition(
        self,
        decision: RouteDecision,
        transition_kind: TransitionKind,
        reason: str = "",
    ) -> RouteTransition:
        """
        Create an explicit RouteTransition record.

        Used when a path promotion occurs after the initial decision
        (e.g., post-response playbook trigger → governed).
        """
        transition = RouteTransition(
            decision_id=decision.decision_id,
            transition_kind=transition_kind,
            reason=reason,
        )
        logger.info(
            "[IngressRouter] transition decision_id=%s kind=%s reason=%s",
            decision.decision_id,
            transition_kind.value,
            reason,
        )
        return transition

    # ─── Internal helpers ───────────────────────────────────────────────

    @staticmethod
    def _mode_to_reason(execution_mode: str) -> RouteReasonCode:
        """Map execution_mode string to a RouteReasonCode."""
        mapping = {
            "qa": RouteReasonCode.EXECUTION_MODE_QA,
            "execution": RouteReasonCode.EXECUTION_MODE_EXECUTION,
            "hybrid": RouteReasonCode.EXECUTION_MODE_HYBRID,
            "meeting": RouteReasonCode.EXECUTION_MODE_MEETING,
        }
        return mapping.get(execution_mode, RouteReasonCode.EXECUTION_MODE_QA)

    @staticmethod
    async def _check_project_meeting(project_id: str, store: Any) -> bool:
        """Check project metadata for meeting_enabled flag."""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            project = await loop.run_in_executor(
                None, lambda: store.get_project(project_id)
            )
            if not project:
                return False
            metadata = getattr(project, "metadata", {}) or {}
            raw = metadata.get("meeting_enabled")
            return raw is True or (isinstance(raw, str) and raw.lower() == "true")
        except Exception as e:
            logger.warning("[IngressRouter] Failed to read project meeting flag: %s", e)
            return False
