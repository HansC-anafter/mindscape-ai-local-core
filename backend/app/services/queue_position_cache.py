import time
from typing import Any, Optional

from sqlalchemy import text as _sa_text

from backend.app.services.task_admission_service import ADMISSION_DEFERRED_REASON


_QUEUE_TOTALS_SQL = """
SELECT COALESCE(queue_shard, 'default') AS queue_shard,
       COUNT(*) AS pending_total,
       COUNT(*) FILTER (
           WHERE next_eligible_at <= NOW()
             AND COALESCE(blocked_reason, '') <> :admission_blocked_reason
       ) AS eligible_total
FROM tasks
WHERE status = 'pending'
  AND task_type IN ('playbook_execution', 'tool_execution')
GROUP BY COALESCE(queue_shard, 'default')
"""

_QUEUE_POSITION_ESTIMATE_SQL = """
SELECT COUNT(*) AS ahead
FROM tasks
WHERE status = 'pending'
  AND task_type IN ('playbook_execution', 'tool_execution')
  AND COALESCE(queue_shard, 'default') = :queue_shard
  AND next_eligible_at <= NOW()
  AND COALESCE(blocked_reason, '') <> :admission_blocked_reason
  AND next_eligible_at < :cutoff
"""


class QueuePositionCache:
    """Process-wide cache for shard totals and targeted queue position estimates."""

    def __init__(self):
        self._positions: dict[str, int] = {}
        self._eligible_totals: dict[str, int] = {}
        self._pending_totals: dict[str, int] = {}
        self._updated: float = 0.0

    def refresh_if_stale(self, tasks_store, max_age: float = 3.0) -> None:
        if time.monotonic() - self._updated < max_age:
            return
        try:
            with tasks_store.get_connection() as conn:
                rows = conn.execute(
                    _sa_text(_QUEUE_TOTALS_SQL),
                    {"admission_blocked_reason": ADMISSION_DEFERRED_REASON},
                ).fetchall()
                self._positions = {}
                self._pending_totals = {str(r[0]): int(r[1]) for r in rows if r[0]}
                self._eligible_totals = {str(r[0]): int(r[2]) for r in rows if r[0]}
                self._updated = time.monotonic()
        except Exception:
            pass

    def get_position(self, tasks_store, task_obj: Any) -> Optional[int]:
        task_id = getattr(task_obj, "id", None)
        if not task_id:
            return None
        if task_id in self._positions:
            return self._positions.get(task_id)

        status_raw = str(getattr(task_obj, "status", "")).lower()
        if "pending" not in status_raw:
            return None
        if getattr(task_obj, "blocked_reason", None):
            return None
        if getattr(task_obj, "frontier_state", None) == "cold":
            return None

        queue_shard = getattr(task_obj, "queue_shard", None) or "default"
        if self.get_total(queue_shard) <= 0:
            return None

        cutoff = (
            getattr(task_obj, "next_eligible_at", None)
            or getattr(task_obj, "created_at", None)
        )
        if cutoff is None:
            return None

        try:
            with tasks_store.get_connection() as conn:
                ahead = conn.execute(
                    _sa_text(_QUEUE_POSITION_ESTIMATE_SQL),
                    {
                        "queue_shard": queue_shard,
                        "cutoff": cutoff,
                        "admission_blocked_reason": ADMISSION_DEFERRED_REASON,
                    },
                ).scalar()
            position = int(ahead or 0) + 1
            self._positions[task_id] = position
            return position
        except Exception:
            return None

    def get_total(self, queue_shard: str) -> int:
        return self._eligible_totals.get(queue_shard or "default", 0)

    @property
    def total(self) -> int:
        return sum(self._eligible_totals.values())


QUEUE_CACHE = QueuePositionCache()
