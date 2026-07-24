import time
import threading
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import text as _sa_text

from backend.app.services.runner_topology import (
    DEFAULT_LOCAL_QUEUE_PARTITION,
    build_queue_partition_filter_clause,
    normalize_queue_partition,
    queue_partition_aliases,
)
from backend.app.services.task_admission_service import ADMISSION_DEFERRED_REASON


QUEUE_READ_STATEMENT_TIMEOUT_MS = 2_000


_QUEUE_TOTALS_SQL = """
SELECT queue_shard AS queue_shard,
       COUNT(*) AS pending_total,
       COUNT(*) AS eligible_total
FROM task_summary_projection
WHERE status = 'pending'
  AND task_type IN ('playbook_execution', 'tool_execution')
  AND frontier_state = 'ready'
  AND next_eligible_at <= :now
  AND (blocked_reason IS NULL OR blocked_reason = '')
GROUP BY queue_shard
"""


def _apply_queue_read_budget(conn: Any) -> None:
    dialect_name = str(getattr(getattr(conn, "dialect", None), "name", ""))
    if dialect_name != "postgresql":
        return
    conn.execute(
        _sa_text(
            "SELECT set_config('statement_timeout', :statement_timeout, true)"
        ),
        {"statement_timeout": f"{QUEUE_READ_STATEMENT_TIMEOUT_MS}ms"},
    )


_QUEUE_POSITION_ESTIMATE_SQL = """
SELECT COUNT(*) AS ahead
FROM task_summary_projection
WHERE status = 'pending'
  AND task_type IN ('playbook_execution', 'tool_execution')
  AND __QUEUE_CLAUSE__
  AND next_eligible_at <= :now
  AND (blocked_reason IS NULL OR blocked_reason = '')
  AND frontier_state = 'ready'
  AND next_eligible_at < :cutoff
"""


class QueuePositionCache:
    """Process-wide cache for shard totals and targeted queue position estimates."""

    def __init__(self):
        self._positions: dict[str, int] = {}
        self._eligible_totals: dict[str, int] = {}
        self._pending_totals: dict[str, int] = {}
        self._updated: float = 0.0
        self._last_attempt: float = 0.0
        self._refresh_lock = threading.Lock()

    def refresh_if_stale(self, tasks_store, max_age: float = 3.0) -> None:
        if time.monotonic() - self._updated < max_age:
            return
        if self._updated <= 0.0:
            acquired = self._refresh_lock.acquire()
        else:
            acquired = self._refresh_lock.acquire(blocking=False)
        if not acquired:
            return
        try:
            if time.monotonic() - self._updated < max_age:
                return
            if time.monotonic() - self._last_attempt < max_age:
                return
            self._last_attempt = time.monotonic()
            with tasks_store.get_connection() as conn:
                _apply_queue_read_budget(conn)
                rows = conn.execute(
                    _sa_text(_QUEUE_TOTALS_SQL),
                    {
                        "admission_blocked_reason": ADMISSION_DEFERRED_REASON,
                        "now": datetime.now(timezone.utc),
                    },
                ).fetchall()
                self._positions = {}
                self._pending_totals = {}
                self._eligible_totals = {}
                for row in rows:
                    canonical = normalize_queue_partition(
                        row[0],
                        fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
                    )
                    self._pending_totals[canonical] = self._pending_totals.get(
                        canonical, 0
                    ) + int(row[1] or 0)
                    self._eligible_totals[canonical] = self._eligible_totals.get(
                        canonical, 0
                    ) + int(row[2] or 0)
                self._updated = time.monotonic()
        except Exception:
            pass
        finally:
            self._refresh_lock.release()

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

        queue_shard = normalize_queue_partition(
            getattr(task_obj, "queue_shard", None),
            fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
        )
        queue_total = self.get_total(queue_shard)
        if queue_total is None or queue_total <= 0:
            return None

        cutoff = (
            getattr(task_obj, "next_eligible_at", None)
            or getattr(task_obj, "created_at", None)
        )
        if cutoff is None:
            return None

        try:
            queue_clause, queue_params = build_queue_partition_filter_clause(
                "queue_shard",
                queue_shard,
                param_prefix="queue_partition",
            )
            with tasks_store.get_connection() as conn:
                _apply_queue_read_budget(conn)
                ahead = conn.execute(
                    _sa_text(
                        _QUEUE_POSITION_ESTIMATE_SQL.replace(
                            "__QUEUE_CLAUSE__", queue_clause
                        )
                    ),
                    {
                        "cutoff": cutoff,
                        "admission_blocked_reason": ADMISSION_DEFERRED_REASON,
                        "now": datetime.now(timezone.utc),
                        **queue_params,
                    },
                ).scalar()
            position = int(ahead or 0) + 1
            self._positions[task_id] = position
            return position
        except Exception:
            return None

    def get_total(self, queue_shard: str) -> Optional[int]:
        if self._updated <= 0.0:
            return None
        raw = str(queue_shard or "").strip()
        canonical = normalize_queue_partition(
            queue_shard,
            fallback=DEFAULT_LOCAL_QUEUE_PARTITION,
        )
        for key in (canonical, *queue_partition_aliases(canonical), raw):
            if key in self._eligible_totals:
                return self._eligible_totals[key]
        return 0

    @property
    def total(self) -> Optional[int]:
        if self._updated <= 0.0:
            return None
        return sum(self._eligible_totals.values())


QUEUE_CACHE = QueuePositionCache()
