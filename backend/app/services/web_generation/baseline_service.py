"""Baseline service for Design Snapshot governance.

Implements baseline management (CRUD) and stale detection based on SemVer.
"""

import logging
import uuid
import json
from datetime import datetime, timezone


def _utc_now():
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)
from typing import Optional, Dict, Any, List, Literal

from sqlalchemy import text

from app.services.stores.postgres_base import PostgresStoreBase
from .version_utils import compare_versions

logger = logging.getLogger(__name__)


class BaselineService(PostgresStoreBase):
    """Service for managing web-generation baselines (Postgres)."""

    def __init__(self, db_path: Optional[str] = None, db_role: str = "core"):
        super().__init__(db_role=db_role)
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        """Initialize database tables (tables should already exist via Alembic migration)."""
        try:
            with self.get_connection() as conn:
                conn.execute(text("SELECT 1 FROM web_generation_baselines LIMIT 1"))
                conn.execute(text("SELECT 1 FROM baseline_events LIMIT 1"))
        except Exception:
            logger.warning(
                "Baseline tables not found. Please run Alembic migration: alembic upgrade head"
            )

    def get_baseline(
        self,
        workspace_id: str,
        project_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Get baseline for workspace/project."""
        with self.get_connection() as conn:
            if project_id:
                row = conn.execute(
                    text(
                        """
                        SELECT * FROM web_generation_baselines
                        WHERE workspace_id = :workspace_id AND project_id = :project_id
                        LIMIT 1
                    """
                    ),
                    {"workspace_id": workspace_id, "project_id": project_id},
                ).fetchone()
                if row:
                    return dict(row._mapping)

            row = conn.execute(
                text(
                    """
                    SELECT * FROM web_generation_baselines
                    WHERE workspace_id = :workspace_id AND project_id IS NULL
                    LIMIT 1
                """
                ),
                {"workspace_id": workspace_id},
            ).fetchone()
            if row:
                return dict(row._mapping)

            return None

    def create_or_update_baseline(
        self,
        workspace_id: str,
        snapshot_id: str,
        variant_id: Optional[str] = None,
        project_id: Optional[str] = None,
        lock_mode: Literal["locked", "advisory"] = "advisory",
        bound_spec_version: Optional[str] = None,
        bound_outline_version: Optional[str] = None,
        updated_by: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create or update baseline."""
        baseline_id = str(uuid.uuid4())
        now = _utc_now()

        with self.transaction() as conn:
            # Check if baseline exists
            if project_id:
                existing = conn.execute(
                    text(
                        """
                        SELECT id FROM web_generation_baselines
                        WHERE workspace_id = :workspace_id AND project_id = :project_id
                    """
                    ),
                    {"workspace_id": workspace_id, "project_id": project_id},
                ).fetchone()
            else:
                existing = conn.execute(
                    text(
                        """
                        SELECT id FROM web_generation_baselines
                        WHERE workspace_id = :workspace_id AND project_id IS NULL
                    """
                    ),
                    {"workspace_id": workspace_id},
                ).fetchone()

            if existing:
                baseline_id = existing._mapping["id"]
                if bound_spec_version is not None or bound_outline_version is not None:
                    current = conn.execute(
                        text(
                            """
                            SELECT bound_spec_version, bound_outline_version
                            FROM web_generation_baselines WHERE id = :id
                        """
                        ),
                        {"id": baseline_id},
                    ).fetchone()
                    final_spec_version = (
                        bound_spec_version
                        if bound_spec_version is not None
                        else current._mapping["bound_spec_version"]
                    )
                    final_outline_version = (
                        bound_outline_version
                        if bound_outline_version is not None
                        else current._mapping["bound_outline_version"]
                    )
                else:
                    current = conn.execute(
                        text(
                            """
                            SELECT bound_spec_version, bound_outline_version
                            FROM web_generation_baselines WHERE id = :id
                        """
                        ),
                        {"id": baseline_id},
                    ).fetchone()
                    final_spec_version = current._mapping["bound_spec_version"]
                    final_outline_version = current._mapping["bound_outline_version"]

                conn.execute(
                    text(
                        """
                        UPDATE web_generation_baselines
                        SET snapshot_id = :snapshot_id,
                            variant_id = :variant_id,
                            lock_mode = :lock_mode,
                            bound_spec_version = :bound_spec_version,
                            bound_outline_version = :bound_outline_version,
                            updated_at = :updated_at,
                            updated_by = :updated_by,
                            notes = :notes
                        WHERE id = :id
                    """
                    ),
                    {
                        "snapshot_id": snapshot_id,
                        "variant_id": variant_id,
                        "lock_mode": lock_mode,
                        "bound_spec_version": final_spec_version,
                        "bound_outline_version": final_outline_version,
                        "updated_at": now,
                        "updated_by": updated_by,
                        "notes": notes,
                        "id": baseline_id,
                    },
                )
            else:
                conn.execute(
                    text(
                        """
                        INSERT INTO web_generation_baselines (
                            id, workspace_id, project_id, snapshot_id, variant_id,
                            lock_mode, bound_spec_version, bound_outline_version,
                            created_at, updated_at, created_by, updated_by, notes
                        ) VALUES (
                            :id, :workspace_id, :project_id, :snapshot_id, :variant_id,
                            :lock_mode, :bound_spec_version, :bound_outline_version,
                            :created_at, :updated_at, :created_by, :updated_by, :notes
                        )
                    """
                    ),
                    {
                        "id": baseline_id,
                        "workspace_id": workspace_id,
                        "project_id": project_id,
                        "snapshot_id": snapshot_id,
                        "variant_id": variant_id,
                        "lock_mode": lock_mode,
                        "bound_spec_version": bound_spec_version,
                        "bound_outline_version": bound_outline_version,
                        "created_at": now,
                        "updated_at": now,
                        "created_by": updated_by,
                        "updated_by": updated_by,
                        "notes": notes,
                    },
                )

        return self.get_baseline(workspace_id, project_id)

    def check_baseline_stale(
        self,
        baseline: Dict[str, Any],
        current_spec_version: Optional[str] = None,
        current_outline_version: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Check if baseline is stale based on version comparison."""
        bound_spec_version = baseline.get("bound_spec_version")
        bound_outline_version = baseline.get("bound_outline_version")

        spec_diff = None
        outline_diff = None
        stale_levels = []
        reasons = []

        if bound_spec_version and current_spec_version:
            spec_diff = compare_versions(bound_spec_version, current_spec_version)
            if spec_diff["level"] in ["major", "minor"] and spec_diff["is_newer"]:
                stale_levels.append(spec_diff["level"])
                reasons.append(
                    f"Spec version drift: {bound_spec_version} -> {current_spec_version}"
                )

        if bound_outline_version and current_outline_version:
            outline_diff = compare_versions(bound_outline_version, current_outline_version)
            if outline_diff["level"] in ["major", "minor"] and outline_diff["is_newer"]:
                stale_levels.append(outline_diff["level"])
                reasons.append(
                    f"Outline version drift: {bound_outline_version} -> {current_outline_version}"
                )

        if not stale_levels:
            return {
                "is_stale": False,
                "severity": None,
                "reason": None,
                "spec_diff": spec_diff,
                "outline_diff": outline_diff,
            }

        severity = "high" if "major" in stale_levels else "medium"
        reason = "; ".join(reasons)

        return {
            "is_stale": True,
            "severity": severity,
            "reason": reason,
            "spec_diff": spec_diff,
            "outline_diff": outline_diff,
        }

    def record_baseline_event(
        self,
        event_type: Literal[
            "baseline.set",
            "baseline.unset",
            "baseline.lock",
            "baseline.unlock",
            "baseline.sync",
            "baseline.variant_change",
        ],
        workspace_id: str,
        snapshot_id: str,
        new_state: Dict[str, Any],
        triggered_by: str,
        project_id: Optional[str] = None,
        variant_id: Optional[str] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        execution_id: Optional[str] = None,
    ) -> str:
        """Record baseline change event for audit trail."""
        event_id = str(uuid.uuid4())
        now = _utc_now()

        previous_state_json = json.dumps(previous_state) if previous_state else None
        new_state_json = json.dumps(new_state)

        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO baseline_events (
                        id, event_type, workspace_id, project_id, snapshot_id, variant_id,
                        previous_state, new_state, reason, triggered_by, triggered_at, execution_id
                    ) VALUES (
                        :id, :event_type, :workspace_id, :project_id, :snapshot_id, :variant_id,
                        :previous_state, :new_state, :reason, :triggered_by, :triggered_at, :execution_id
                    )
                """
                ),
                {
                    "id": event_id,
                    "event_type": event_type,
                    "workspace_id": workspace_id,
                    "project_id": project_id,
                    "snapshot_id": snapshot_id,
                    "variant_id": variant_id,
                    "previous_state": previous_state_json,
                    "new_state": new_state_json,
                    "reason": reason,
                    "triggered_by": triggered_by,
                    "triggered_at": now,
                    "execution_id": execution_id,
                },
            )

        return event_id

    def list_baseline_events(
        self,
        workspace_id: str,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List baseline events for audit trail."""
        with self.get_connection() as conn:
            if project_id:
                rows = conn.execute(
                    text(
                        """
                        SELECT * FROM baseline_events
                        WHERE workspace_id = :workspace_id AND project_id = :project_id
                        ORDER BY triggered_at DESC
                        LIMIT :limit
                    """
                    ),
                    {
                        "workspace_id": workspace_id,
                        "project_id": project_id,
                        "limit": limit,
                    },
                ).fetchall()
            else:
                rows = conn.execute(
                    text(
                        """
                        SELECT * FROM baseline_events
                        WHERE workspace_id = :workspace_id AND (project_id = :project_id OR project_id IS NULL)
                        ORDER BY triggered_at DESC
                        LIMIT :limit
                    """
                    ),
                    {
                        "workspace_id": workspace_id,
                        "project_id": project_id,
                        "limit": limit,
                    },
                ).fetchall()

            events = []
            for row in rows:
                event = dict(row._mapping)
                if event.get("previous_state"):
                    event["previous_state"] = json.loads(event["previous_state"])
                if event.get("new_state"):
                    event["new_state"] = json.loads(event["new_state"])
                events.append(event)

            return events
