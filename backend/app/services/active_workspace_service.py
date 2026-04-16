"""Helpers for selecting workspaces that currently need a live CLI bridge."""

from __future__ import annotations

import logging
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

_DEFAULT_ACTIVE_WINDOW_MINUTES = 24 * 60


def _window_minutes(env_name: str, default: int = _DEFAULT_ACTIVE_WINDOW_MINUTES) -> int:
    raw = str(os.getenv(env_name, default)).strip()
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


COMPILE_ACTIVE_WINDOW = timedelta(
    minutes=_window_minutes("MINDSCAPE_ACTIVE_COMPILE_WINDOW_MINUTES")
)
MEETING_ACTIVE_WINDOW = timedelta(
    minutes=_window_minutes("MINDSCAPE_ACTIVE_MEETING_WINDOW_MINUTES")
)
DISPATCH_ACTIVE_WINDOW = timedelta(
    minutes=_window_minutes("MINDSCAPE_ACTIVE_DISPATCH_WINDOW_MINUTES")
)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_datetime(raw: Any) -> Optional[datetime]:
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=timezone.utc)
    if isinstance(raw, str):
        normalized = raw.strip()
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _row_mapping(row: Any) -> Dict[str, Any]:
    if hasattr(row, "_mapping"):
        return dict(row._mapping)
    if isinstance(row, dict):
        return dict(row)
    if isinstance(row, (list, tuple)):
        return {"workspace_id": row[0] if row else None}
    return {
        "workspace_id": getattr(row, "workspace_id", None),
        "updated_at": getattr(row, "updated_at", None),
        "started_at": getattr(row, "started_at", None),
        "created_at": getattr(row, "created_at", None),
        "picked_at": getattr(row, "picked_at", None),
        "last_progress_at": getattr(row, "last_progress_at", None),
        "metadata": getattr(row, "metadata", None),
    }


def _latest_timestamp(*values: Any) -> Optional[datetime]:
    candidates = [ts for ts in (_coerce_datetime(value) for value in values) if ts]
    if not candidates:
        return None
    return max(candidates)


def _meeting_metadata_timestamp(metadata: Any) -> Optional[datetime]:
    if not isinstance(metadata, dict):
        return None
    return _latest_timestamp(
        metadata.get("last_round_updated_at"),
        metadata.get("pipeline_stage_updated_at"),
    )


def _is_recent(timestamp: Optional[datetime], *, now: datetime, window: timedelta) -> bool:
    if timestamp is None:
        return False
    return timestamp >= (now - window)


def workspace_uses_surface(workspace: Any, surface: Optional[str]) -> bool:
    normalized_surface = str(surface or "").strip()
    if not normalized_surface:
        return True

    resolved_runtime = getattr(workspace, "resolved_executor_runtime", None)
    if resolved_runtime == normalized_surface:
        return True

    legacy_runtime = getattr(workspace, "executor_runtime", None)
    if legacy_runtime == normalized_surface:
        return True

    for raw_spec in getattr(workspace, "executor_specs", None) or []:
        if isinstance(raw_spec, dict) and raw_spec.get("runtime_id") == normalized_surface:
            return True
    return False


def _safe_rows(
    db: Session,
    query: str,
    params: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    try:
        rows = db.execute(text(query), params or {}).fetchall()
    except Exception:
        logger.debug("Active workspace query failed", exc_info=True)
        return []
    return [_row_mapping(row) for row in rows]


def build_active_workspace_payload(
    *,
    workspaces: List[Any],
    db: Session,
    surface: Optional[str] = None,
) -> List[Dict[str, Any]]:
    workspace_map = {ws.id: ws for ws in workspaces}
    reasons: Dict[str, set[str]] = defaultdict(set)
    now = _utc_now()

    for row in _safe_rows(
        db,
        """
        SELECT workspace_id, updated_at, started_at, created_at
        FROM compile_jobs
        WHERE status IN ('accepted', 'running')
        """,
    ):
        workspace_id = row.get("workspace_id")
        if not workspace_id:
            continue
        activity_at = _latest_timestamp(
            row.get("updated_at"),
            row.get("started_at"),
            row.get("created_at"),
        )
        if not _is_recent(activity_at, now=now, window=COMPILE_ACTIVE_WINDOW):
            continue
        reasons[workspace_id].add("compile_incomplete")

    for row in _safe_rows(
        db,
        """
        SELECT workspace_id, started_at, metadata
        FROM meeting_sessions
        WHERE ended_at IS NULL
          AND status IN ('planned', 'active', 'closing')
        """,
    ):
        workspace_id = row.get("workspace_id")
        if not workspace_id:
            continue
        activity_at = _latest_timestamp(
            row.get("started_at"),
            _meeting_metadata_timestamp(row.get("metadata")),
        )
        if not _is_recent(activity_at, now=now, window=MEETING_ACTIVE_WINDOW):
            continue
        reasons[workspace_id].add("meeting_active")

    dispatch_sql = """
        SELECT workspace_id, created_at, picked_at, last_progress_at
        FROM pending_dispatch
        WHERE completed_at IS NULL
          AND status IN ('pending', 'picked')
    """
    dispatch_params: Dict[str, Any] = {}
    if surface:
        dispatch_sql += " AND (surface_type IS NULL OR surface_type = :surface)"
        dispatch_params["surface"] = surface
    for row in _safe_rows(db, dispatch_sql, dispatch_params):
        workspace_id = row.get("workspace_id")
        if not workspace_id:
            continue
        activity_at = _latest_timestamp(
            row.get("last_progress_at"),
            row.get("picked_at"),
            row.get("created_at"),
        )
        if not _is_recent(activity_at, now=now, window=DISPATCH_ACTIVE_WINDOW):
            continue
        reasons[workspace_id].add("dispatch_pending")

    payload: List[Dict[str, Any]] = []
    for workspace_id, workspace_reasons in reasons.items():
        workspace = workspace_map.get(workspace_id)
        if workspace is None:
            continue
        if surface and not (
            workspace_uses_surface(workspace, surface)
            or "dispatch_pending" in workspace_reasons
        ):
            continue
        payload.append(
            {
                "id": workspace.id,
                "title": workspace.title,
                "surface": surface,
                "active_reasons": sorted(workspace_reasons),
            }
        )

    payload.sort(key=lambda item: item["id"])
    return payload
