"""Shared restart safety checks for install and validation flows."""

from __future__ import annotations

import logging
from typing import Any, Dict

from sqlalchemy import text

logger = logging.getLogger(__name__)


def inspect_restart_blockers() -> Dict[str, Any]:
    """Return whether an automatic backend restart should be deferred."""
    try:
        from app.services.stores.compile_job_store import CompileJobStore

        store = CompileJobStore()
        with store.get_connection() as conn:
            active_compile_jobs = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM compile_jobs
                        WHERE status IN ('accepted', 'running')
                        """
                    )
                ).scalar()
                or 0
            )
            active_meeting_sessions = _count_fresh_meeting_sessions(conn)
            active_pending_dispatch = int(
                conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM pending_dispatch
                        WHERE status IN ('pending', 'no_client', 'picked')
                          AND completed_at IS NULL
                        """
                    )
                ).scalar()
                or 0
            )
        if (
            active_compile_jobs > 0
            or active_meeting_sessions > 0
            or active_pending_dispatch > 0
        ):
            return {
                "blocked": True,
                "reason": "active_workloads",
                "active_compile_jobs": active_compile_jobs,
                "active_meeting_sessions": active_meeting_sessions,
                "active_pending_dispatch": active_pending_dispatch,
            }
        return {
            "blocked": False,
            "active_compile_jobs": 0,
            "active_meeting_sessions": 0,
            "active_pending_dispatch": 0,
        }
    except Exception as exc:
        logger.warning("Failed to inspect restart blockers: %s", exc)
        return {
            "blocked": True,
            "reason": "blocker_inspection_failed",
            "error": str(exc),
            "active_compile_jobs": None,
            "active_meeting_sessions": None,
            "active_pending_dispatch": None,
        }


def format_restart_blocker_detail(blockers: Dict[str, Any]) -> str:
    """Format restart blockers for logs and install warnings."""
    fragments = []
    for key, label in (
        ("active_compile_jobs", "compile_jobs"),
        ("active_meeting_sessions", "meeting_sessions"),
        ("active_pending_dispatch", "pending_dispatch"),
    ):
        count = blockers.get(key)
        if isinstance(count, int) and count > 0:
            fragments.append(f"{label}={count}")
    if fragments:
        return ", ".join(fragments)
    if blockers.get("error"):
        return str(blockers["error"])
    return "unknown workload counts"


def _count_fresh_meeting_sessions(conn: Any) -> int:
    query = text(
        """
        WITH candidates AS (
            SELECT
                status,
                started_at,
                CASE
                    WHEN metadata->>'last_round_updated_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN (metadata->>'last_round_updated_at')::timestamptz
                    ELSE NULL
                END AS last_round_updated_at,
                CASE
                    WHEN metadata->>'pipeline_stage_updated_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN (metadata->>'pipeline_stage_updated_at')::timestamptz
                    ELSE NULL
                END AS pipeline_stage_updated_at,
                CASE
                    WHEN metadata->>'dispatch_updated_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN (metadata->>'dispatch_updated_at')::timestamptz
                    ELSE NULL
                END AS dispatch_updated_at,
                CASE
                    WHEN metadata->>'updated_at' ~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}'
                    THEN (metadata->>'updated_at')::timestamptz
                    ELSE NULL
                END AS metadata_updated_at
            FROM meeting_sessions
            WHERE ended_at IS NULL
              AND status IN ('planned', 'active', 'closing')
        ),
        activity AS (
            SELECT
                status,
                GREATEST(
                    started_at,
                    COALESCE(last_round_updated_at, started_at),
                    COALESCE(pipeline_stage_updated_at, started_at),
                    COALESCE(dispatch_updated_at, started_at),
                    COALESCE(metadata_updated_at, started_at)
                ) AS last_activity_at
            FROM candidates
        )
        SELECT COUNT(*)
        FROM activity
        WHERE last_activity_at >= now() - (
            CASE
                WHEN status = 'planned' THEN interval '15 minutes'
                ELSE interval '30 minutes'
            END
        )
        """
    )
    return int(conn.execute(query).scalar() or 0)
