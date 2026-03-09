"""
MeetingExecutionContext — resolved snapshot of runtime inputs for meeting.

Aggregates from existing models:
- workspace.core: executor_specs, fallback_model, resolved_executor_runtime
- workspace_runtime_profile: loop_budget, recovery_policy
- runtime_environment: auth_type, auth_status
- route_decision: route_kind, execution_profile
- RuntimeObservabilitySnapshot: runtime visibility

Not persisted — assembled fresh at each meeting start by PipelineCore.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, PrivateAttr


class MeetingExecutionContext(BaseModel):
    """Resolved execution context snapshot for a meeting session.

    Assembled by PipelineCore from existing workspace, profile,
    runtime, and routing models.  Read-only within MeetingEngine.
    """

    # From Workspace.executor_specs + fallback_model
    executor_runtime_id: Optional[str] = Field(
        default=None,
        description="Resolved executor runtime ID",
    )
    executor_specs: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="Executor spec entries from workspace",
    )
    fallback_model: Optional[str] = Field(
        default=None,
        description="Fallback model for generation",
    )

    # From RuntimeEnvironment
    auth_type: str = Field(
        default="none",
        description="Auth type: api_key | oauth2 | cli_bridge | none",
    )
    auth_status: str = Field(
        default="disconnected",
        description="Auth status: connected | disconnected | error",
    )

    # From WorkspaceRuntimeProfile.loop_budget
    token_budget: Optional[int] = Field(
        default=None,
        description="Maximum token budget for this session",
    )
    cost_budget: Optional[float] = Field(
        default=None,
        description="Maximum cost budget (USD) for this session",
    )
    time_budget_seconds: Optional[int] = Field(
        default=None,
        description="Maximum time budget in seconds",
    )
    max_iterations: int = Field(
        default=5,
        description="Maximum meeting rounds / iterations",
    )

    # From WorkspaceRuntimeProfile.recovery_policy
    retry_strategy: str = Field(
        default="immediate",
        description="Recovery strategy: immediate | exponential_backoff | ask_user",
    )
    max_retries: int = Field(
        default=2,
        description="Maximum retry count per failed phase",
    )

    # From RouteDecision
    route_kind: str = Field(
        default="meeting",
        description="Route kind: fast | governed | meeting",
    )
    execution_profile: str = Field(
        default="durable",
        description="Execution profile: simple | durable",
    )

    # RuntimeObservabilitySnapshot (read-only)
    runtime_snapshot: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Serialized RuntimeObservabilitySnapshot",
    )

    # Timing (for budget_headroom_pct computation)
    _assembled_at: float = PrivateAttr(default=0.0)

    @property
    def budget_headroom_pct(self) -> float:
        """Fraction of time budget remaining (0.0–1.0).

        Returns 1.0 if no budget is set.
        Used by select_deliberation_depth().
        """
        if not self.time_budget_seconds or self.time_budget_seconds <= 0:
            return 1.0
        if self._assembled_at <= 0:
            return 1.0
        elapsed = time.monotonic() - self._assembled_at
        remaining = max(0.0, self.time_budget_seconds - elapsed)
        return remaining / self.time_budget_seconds

    @classmethod
    def assemble(
        cls,
        workspace: Any = None,
        runtime_profile: Any = None,
        runtime_env: Any = None,
        route_decision: Any = None,
        runtime_snapshot: Any = None,
    ) -> "MeetingExecutionContext":
        """Assemble from existing domain models.

        Each source is optional — missing sources use safe defaults.
        """
        ctx = cls()
        ctx._assembled_at = time.monotonic()

        # Workspace
        if workspace:
            ctx.executor_runtime_id = getattr(
                workspace, "resolved_executor_runtime", None
            )
            ctx.executor_specs = getattr(workspace, "executor_specs", []) or []
            ctx.fallback_model = getattr(workspace, "fallback_model", None)

        # RuntimeEnvironment
        if runtime_env:
            ctx.auth_type = getattr(runtime_env, "auth_type", "none") or "none"
            ctx.auth_status = (
                getattr(runtime_env, "auth_status", "disconnected") or "disconnected"
            )

        # WorkspaceRuntimeProfile
        if runtime_profile:
            loop_budget = getattr(runtime_profile, "loop_budget", None)
            if loop_budget:
                ctx.token_budget = getattr(loop_budget, "token_budget", None)
                ctx.cost_budget = getattr(loop_budget, "cost_budget", None)
                ctx.time_budget_seconds = getattr(
                    loop_budget, "time_budget_seconds", None
                )
                ctx.max_iterations = getattr(loop_budget, "max_iterations", 5)

            recovery = getattr(runtime_profile, "recovery_policy", None)
            if recovery:
                ctx.retry_strategy = (
                    getattr(recovery, "retry_strategy", "immediate") or "immediate"
                )
                ctx.max_retries = getattr(recovery, "max_retries", 2)

        # RouteDecision
        if route_decision:
            kind = getattr(route_decision, "route_kind", None)
            if kind:
                ctx.route_kind = kind.value if hasattr(kind, "value") else str(kind)
            profile = getattr(route_decision, "execution_profile", None)
            if profile:
                ctx.execution_profile = (
                    profile.value if hasattr(profile, "value") else str(profile)
                )

        # RuntimeObservabilitySnapshot
        if runtime_snapshot is not None:
            if hasattr(runtime_snapshot, "model_dump"):
                ctx.runtime_snapshot = runtime_snapshot.model_dump(mode="json")
            elif isinstance(runtime_snapshot, dict):
                ctx.runtime_snapshot = runtime_snapshot

            # Backfill auth_type/auth_status from snapshot when runtime_env wasn't passed
            if runtime_env is None and ctx.runtime_snapshot:
                snap = ctx.runtime_snapshot
                if snap.get("auth_type"):
                    ctx.auth_type = snap["auth_type"]
                if snap.get("auth_status"):
                    ctx.auth_status = snap["auth_status"]

        return ctx
