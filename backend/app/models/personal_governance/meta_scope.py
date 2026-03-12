"""
MetaScope — dynamic governance range selector (L4).

Defines which workspaces, projects, inboxes, and time window to include
in a meta meeting session. Includes snapshot capability for replay.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class MetaScope:
    """A dynamic governance range selector for meta meetings."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    owner_profile_id: str = ""

    # --- Selector ---
    scope_kind: str = "manual"  # "manual" | "rule_based" | "adaptive"
    included_workspaces: List[str] = field(default_factory=list)
    included_projects: List[str] = field(default_factory=list)
    included_inboxes: List[str] = field(
        default_factory=list
    )  # "chat_capture" | "uploads" | "external_docs"
    time_window: str = "7d"  # "7d" | "30d" | ISO range
    goal_horizon: str = "open-ended"  # "today" | "week" | "quarter" | "open-ended"
    purpose: str = (
        "review"  # "review" | "planning" | "alignment" | "dispatch" | "cleanup"
    )

    # --- Snapshot (ADR Gap 4) ---
    scope_snapshot_at: Optional[datetime] = None
    scope_resolution_strategy: str = (
        "latest_at_snapshot"  # "latest_at_snapshot" | "time_window_bound"
    )
    resolved_digest_ids: List[str] = field(default_factory=list)
    resolved_workspace_states: Dict[str, Any] = field(default_factory=dict)

    # --- Metadata ---
    created_at: datetime = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def freeze_snapshot(self) -> None:
        """Freeze the current scope for replay."""
        self.scope_snapshot_at = _utc_now()
