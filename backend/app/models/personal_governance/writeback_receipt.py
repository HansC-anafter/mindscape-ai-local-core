"""
WritebackReceipt — audit trail for meta meeting writeback operations.

Every writeback from a meta meeting to L3/L4 targets produces a receipt
for traceability and debugging.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass
class WritebackReceipt:
    """Tracks a single writeback operation from meta meeting to target table."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    meta_session_id: str = ""
    source_decision_id: str = ""  # MeetingDecision.id that triggered this

    target_table: str = (
        ""  # "goal_ledger" | "personal_knowledge" | "review_history" | "dispatch_task"
    )
    target_id: str = ""  # row ID in target table
    writeback_type: str = ""  # "append" | "candidate" | "record" | "dispatch"

    status: str = (
        "completed"  # "completed" | "pending_confirmation" | "rejected" | "failed"
    )
    error_detail: Optional[str] = None

    created_at: datetime = field(default_factory=_utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)
