"""Meeting Supervisor — post-session quality gate and stuck-task detection.

Part of L5 supervision layer for the meeting engine.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MeetingSupervisor:
    """Post-session quality gate and stuck-task detection.

    Responsibilities:
    - Check dispatch outcomes after session close
    - Detect stuck tasks that haven't progressed
    - Score session quality based on action item completion
    """

    def __init__(self, tasks_store, session_store=None):
        """Initialize with required stores.

        Args:
            tasks_store: Store with list_tasks_by_meeting_session method.
            session_store: Optional session store for metadata updates.
        """
        self._tasks_store = tasks_store
        self._session_store = session_store

    async def on_session_closed(self, session_id: str) -> Dict[str, Any]:
        """Called after a meeting session closes.

        Queries all tasks spawned by this session, checks for stuck/failed
        tasks, and computes a session quality score.

        Args:
            session_id: Meeting session ID.

        Returns:
            Session summary with task counts and quality score.
        """
        tasks = self._tasks_store.list_tasks_by_meeting_session(session_id)

        # Read session metadata FIRST (before early return on total==0)
        # because playbook launches may exist even when no tasks were created
        playbook_launches = 0
        file_coverage_gaps = 0
        if self._session_store:
            try:
                session = self._session_store.get_by_id(session_id)
                if session:
                    meta = session.metadata or {}
                    exec_ids = meta.get("execution_ids", [])
                    playbook_launches = len(exec_ids)
                    warnings = meta.get("tool_coverage_warnings", [])
                    file_coverage_gaps = len(warnings)
            except Exception as exc:
                logger.warning("Failed to read session metadata for coverage: %s", exc)

        total = len(tasks)
        if total == 0 and playbook_launches == 0:
            return {
                "session_id": session_id,
                "total_tasks": 0,
                "succeeded": 0,
                "failed": 0,
                "stuck": 0,
                "score": 1.0,
                "tool_tasks": 0,
                "playbook_launches": playbook_launches,
                "tool_coverage": 0.0,
                "file_coverage_gaps": file_coverage_gaps,
            }

        succeeded = sum(1 for t in tasks if t.status == "succeeded")
        failed = sum(1 for t in tasks if t.status == "failed")
        stuck = self._count_stuck(tasks)
        score = self.compute_score(succeeded, failed, total)

        # Tool coverage: tasks with tool_name in execution_context
        tool_tasks = sum(
            1
            for t in tasks
            if (getattr(t, "execution_context", None) or {}).get("tool_name")
        )

        # playbook_launches and file_coverage_gaps already read above

        return {
            "session_id": session_id,
            "total_tasks": total,
            "succeeded": succeeded,
            "failed": failed,
            "stuck": stuck,
            "score": round(score, 2),
            "tool_tasks": tool_tasks,
            "playbook_launches": playbook_launches,
            "tool_coverage": (
                (tool_tasks + playbook_launches) / (total + playbook_launches)
                if (total + playbook_launches) > 0
                else 0.0
            ),
            "file_coverage_gaps": file_coverage_gaps,
        }

    async def check_stuck_tasks(
        self,
        session_id: str,
        stuck_threshold_minutes: int = 30,
    ) -> List[Dict[str, Any]]:
        """Find tasks from session that haven't progressed beyond threshold.

        Args:
            session_id: Meeting session ID.
            stuck_threshold_minutes: Minutes without progress to be considered stuck.

        Returns:
            List of stuck task summaries.
        """
        tasks = self._tasks_store.list_tasks_by_meeting_session(session_id)
        threshold = datetime.now(timezone.utc) - timedelta(
            minutes=stuck_threshold_minutes
        )

        stuck = []
        for task in tasks:
            if task.status not in ("pending", "running"):
                continue
            updated = getattr(task, "updated_at", None)
            if updated and updated < threshold:
                stuck.append(
                    {
                        "task_id": task.id,
                        "title": getattr(task, "title", ""),
                        "status": task.status,
                        "updated_at": updated.isoformat() if updated else None,
                        "minutes_stuck": int(
                            (datetime.now(timezone.utc) - updated).total_seconds() / 60
                        ),
                    }
                )
        return stuck

    async def score_session(self, session_id: str) -> float:
        """Compute quality score for session based on action item outcomes.

        Score = completed / total, bounded [0, 1].
        Empty sessions score 1.0 (no failures).

        Args:
            session_id: Meeting session ID.

        Returns:
            Quality score between 0.0 and 1.0.
        """
        tasks = self._tasks_store.list_tasks_by_meeting_session(session_id)
        total = len(tasks)
        if total == 0:
            return 1.0
        succeeded = sum(1 for t in tasks if t.status == "succeeded")
        failed = sum(1 for t in tasks if t.status == "failed")
        return self.compute_score(succeeded, failed, total)

    @staticmethod
    def compute_score(completed: int, failed: int, total: int) -> float:
        """Compute quality score.

        Pure function for testability.
        """
        if total == 0:
            return 1.0
        return completed / total

    @staticmethod
    def _count_stuck(tasks, threshold_minutes: int = 30) -> int:
        """Count tasks that appear stuck (pending/running beyond threshold)."""
        threshold = datetime.now(timezone.utc) - timedelta(minutes=threshold_minutes)
        count = 0
        for task in tasks:
            if task.status not in ("pending", "running"):
                continue
            updated = getattr(task, "updated_at", None)
            if updated and updated < threshold:
                count += 1
        return count
