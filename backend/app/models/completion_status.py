"""
ExecutionCompletionStatus — honest completion semantics for meeting engine.

Tracks the lifecycle of dispatched tasks INDEPENDENTLY of the meeting
session FSM (active → closed).  The meeting can close while tasks
are still ``RUNNING`` or ``ACCEPTED``.

This is execution-level state, not session state.
"""

from __future__ import annotations

from enum import Enum


class ExecutionCompletionStatus(str, Enum):
    """Completion status of all tasks dispatched by a meeting session.

    Lifecycle:
        ACCEPTED → RUNNING → COMPLETED
                          ↘ FAILED

    - ACCEPTED:  Meeting closed, tasks dispatched, no worker progress yet
    - RUNNING:   At least one dispatched task has started execution
    - COMPLETED: All dispatched tasks reached terminal success
    - FAILED:    Terminal failure in meeting, dispatch, or downstream execution
    """

    ACCEPTED = "accepted"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

    @classmethod
    def from_task_statuses(
        cls, statuses: list[str], *, has_dispatched: bool = True
    ) -> "ExecutionCompletionStatus":
        """Derive completion status from a list of downstream task statuses.

        Args:
            statuses: List of task status strings from dispatched tasks.
            has_dispatched: Whether any tasks were dispatched at all.

        Returns:
            The aggregate ExecutionCompletionStatus.
        """
        if not has_dispatched or not statuses:
            return cls.COMPLETED  # no tasks → trivially complete

        terminal = {"completed", "succeeded", "failed", "cancelled", "skipped"}
        running = {"running", "dispatched", "queued", "pending"}

        all_terminal = all(s in terminal for s in statuses)
        has_failure = any(s in ("failed", "cancelled") for s in statuses)
        has_running = any(s in running for s in statuses)

        if all_terminal:
            return cls.FAILED if has_failure else cls.COMPLETED
        if has_running:
            return cls.RUNNING
        return cls.ACCEPTED
