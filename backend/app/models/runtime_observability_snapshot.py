"""
RuntimeObservabilitySnapshot — read-only view of selected runtime state.

Assembled ONCE at meeting start, read by MeetingExecutionContext
and budget-aware gating (via SupervisionSignals).

Sources: RuntimeEnvironment (DB model) + RuntimeAuthService.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field


class RuntimeObservabilitySnapshot(BaseModel):
    """Point-in-time observability snapshot of the selected executor runtime.

    Assembled by PipelineCore from RuntimeEnvironment + RuntimeAuthService.
    """

    # Identity
    selected_runtime_id: Optional[str] = Field(
        default=None,
        description="ID of the runtime selected for this session",
    )
    selection_reason: str = Field(
        default="default",
        description="Why this runtime was selected (primary | pool_rotation | fallback | default)",
    )
    runtime_name: Optional[str] = Field(
        default=None,
        description="Human-readable name of the runtime",
    )

    # Auth
    auth_type: str = Field(
        default="none",
        description="api_key | oauth2 | cli_bridge | none",
    )
    auth_status: str = Field(
        default="disconnected",
        description="connected | disconnected | pending | error",
    )

    # Availability
    is_available: bool = Field(
        default=False,
        description="True if runtime is active, auth connected, not in cooldown",
    )
    cooldown_until: Optional[datetime] = Field(
        default=None,
        description="If in cooldown, when it expires",
    )
    last_error_code: Optional[str] = Field(
        default=None,
        description="Last error code from runtime (quota_exceeded, auth_failed, etc.)",
    )

    # Pool
    pool_group: Optional[str] = Field(
        default=None,
        description="Pool group if multi-account rotation is active",
    )
    pool_priority: int = Field(
        default=0,
        description="Priority within pool group (lower = higher priority)",
    )

    # Timing
    last_used_at: Optional[datetime] = Field(
        default=None,
        description="Last time this runtime was used",
    )
    snapshot_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When this snapshot was taken",
    )

    @classmethod
    def from_runtime_environment(
        cls,
        runtime: Any,
        selection_reason: str = "default",
    ) -> "RuntimeObservabilitySnapshot":
        """Build snapshot from a RuntimeEnvironment DB model."""
        if runtime is None:
            return cls()

        now = datetime.now(timezone.utc)
        cooldown = getattr(runtime, "cooldown_until", None)
        in_cooldown = cooldown is not None and cooldown > now

        auth_status = getattr(runtime, "auth_status", "disconnected") or "disconnected"
        status = getattr(runtime, "status", "not_configured") or "not_configured"

        is_available = (
            status in ("active", "configured")
            and auth_status == "connected"
            and not in_cooldown
        )

        return cls(
            selected_runtime_id=getattr(runtime, "id", None),
            selection_reason=selection_reason,
            runtime_name=getattr(runtime, "name", None),
            auth_type=getattr(runtime, "auth_type", "none") or "none",
            auth_status=auth_status,
            is_available=is_available,
            cooldown_until=cooldown if in_cooldown else None,
            last_error_code=getattr(runtime, "last_error_code", None),
            pool_group=getattr(runtime, "pool_group", None),
            pool_priority=getattr(runtime, "pool_priority", 0) or 0,
            last_used_at=getattr(runtime, "last_used_at", None),
            snapshot_at=now,
        )
