"""Baseline service for Design Snapshot governance.

Implements baseline management (CRUD) and stale detection based on SemVer.
"""

import logging
import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from contextlib import contextmanager

from .version_utils import compare_versions

logger = logging.getLogger(__name__)


class BaselineService:
    """Service for managing web-generation baselines."""

    def __init__(self, db_path: str = None):
        """Initialize baseline service."""
        import os
        if db_path is None:
            if os.path.exists('/.dockerenv') or os.environ.get('PYTHONPATH') == '/app':
                db_path = '/app/data/mindscape.db'
            else:
                base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))
                data_dir = os.path.join(base_dir, "data")
                os.makedirs(data_dir, exist_ok=True)
                db_path = os.path.join(data_dir, "mindscape.db")

        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_connection(self):
        """Get database connection with proper cleanup."""
        import sqlite3
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def _init_db(self):
        """Initialize database tables (tables should already exist via Alembic migration)."""
        # Tables are created by Alembic migration, so we just verify they exist
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute("SELECT 1 FROM web_generation_baselines LIMIT 1")
                cursor.execute("SELECT 1 FROM baseline_events LIMIT 1")
            except Exception:
                logger.warning("Baseline tables not found. Please run Alembic migration: alembic upgrade head")

    def get_baseline(
        self,
        workspace_id: str,
        project_id: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Get baseline for workspace/project.

        Priority:
        1. Project-specific baseline
        2. Workspace-level default (project_id is NULL)
        3. None if not found

        Returns:
            Baseline dict with all fields, or None if not found
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Try project-specific first
            if project_id:
                cursor.execute("""
                    SELECT * FROM web_generation_baselines
                    WHERE workspace_id = ? AND project_id = ?
                    LIMIT 1
                """, (workspace_id, project_id))
                row = cursor.fetchone()
                if row:
                    return dict(row)

            # Fall back to workspace-level default (project_id is NULL)
            cursor.execute("""
                SELECT * FROM web_generation_baselines
                WHERE workspace_id = ? AND project_id IS NULL
                LIMIT 1
            """, (workspace_id,))
            row = cursor.fetchone()
            if row:
                return dict(row)

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
        notes: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create or update baseline.

        Uses UPSERT: if baseline exists for workspace_id + project_id, update it;
        otherwise create new one.
        """
        baseline_id = str(uuid.uuid4())
        now = datetime.utcnow()

        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Check if baseline exists
            if project_id:
                cursor.execute("""
                    SELECT id FROM web_generation_baselines
                    WHERE workspace_id = ? AND project_id = ?
                """, (workspace_id, project_id))
            else:
                cursor.execute("""
                    SELECT id FROM web_generation_baselines
                    WHERE workspace_id = ? AND project_id IS NULL
                """, (workspace_id,))

            existing = cursor.fetchone()

            if existing:
                # Update existing
                baseline_id = existing['id']
                # Only update bound versions if explicitly provided (not None)
                if bound_spec_version is not None or bound_outline_version is not None:
                    # Get current values to preserve if new values are None
                    cursor.execute("SELECT bound_spec_version, bound_outline_version FROM web_generation_baselines WHERE id = ?", (baseline_id,))
                    current = cursor.fetchone()
                    final_spec_version = bound_spec_version if bound_spec_version is not None else current[0]
                    final_outline_version = bound_outline_version if bound_outline_version is not None else current[1]
                else:
                    # Preserve existing values
                    cursor.execute("SELECT bound_spec_version, bound_outline_version FROM web_generation_baselines WHERE id = ?", (baseline_id,))
                    current = cursor.fetchone()
                    final_spec_version = current[0]
                    final_outline_version = current[1]

                cursor.execute("""
                    UPDATE web_generation_baselines
                    SET snapshot_id = ?,
                        variant_id = ?,
                        lock_mode = ?,
                        bound_spec_version = ?,
                        bound_outline_version = ?,
                        updated_at = ?,
                        updated_by = ?,
                        notes = ?
                    WHERE id = ?
                """, (
                    snapshot_id,
                    variant_id,
                    lock_mode,
                    final_spec_version,
                    final_outline_version,
                    now,
                    updated_by,
                    notes,
                    baseline_id
                ))
            else:
                # Create new
                cursor.execute("""
                    INSERT INTO web_generation_baselines (
                        id, workspace_id, project_id, snapshot_id, variant_id,
                        lock_mode, bound_spec_version, bound_outline_version,
                        created_at, updated_at, created_by, updated_by, notes
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    baseline_id,
                    workspace_id,
                    project_id,
                    snapshot_id,
                    variant_id,
                    lock_mode,
                    bound_spec_version,
                    bound_outline_version,
                    now,
                    now,
                    updated_by,
                    updated_by,
                    notes
                ))

            conn.commit()

        # Return updated baseline
        return self.get_baseline(workspace_id, project_id)

    def check_baseline_stale(
        self,
        baseline: Dict[str, Any],
        current_spec_version: Optional[str] = None,
        current_outline_version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Check if baseline is stale based on version comparison.

        Returns:
        {
            "is_stale": bool,
            "severity": "high" | "medium" | None,
            "reason": str,
            "spec_diff": {...},
            "outline_diff": {...}
        }

        Stale rules:
        - MAJOR bump → must re-sync (stale = True, severity = "high")
        - MINOR bump → recommended re-sync (stale = True, severity = "medium")
        - PATCH bump → not stale (stale = False)
        """
        bound_spec_version = baseline.get("bound_spec_version")
        bound_outline_version = baseline.get("bound_outline_version")

        spec_diff = None
        outline_diff = None
        stale_levels = []
        reasons = []

        # Check spec version
        if bound_spec_version and current_spec_version:
            spec_diff = compare_versions(bound_spec_version, current_spec_version)
            if spec_diff["level"] in ["major", "minor"] and spec_diff["is_newer"]:
                stale_levels.append(spec_diff["level"])
                reasons.append(f"Spec: {spec_diff['reason']}")

        # Check outline version
        if bound_outline_version and current_outline_version:
            outline_diff = compare_versions(bound_outline_version, current_outline_version)
            if outline_diff["level"] in ["major", "minor"] and outline_diff["is_newer"]:
                stale_levels.append(outline_diff["level"])
                reasons.append(f"Outline: {outline_diff['reason']}")

        # Determine stale status
        if not stale_levels:
            return {
                "is_stale": False,
                "severity": None,
                "reason": "No version changes detected",
                "spec_diff": spec_diff,
                "outline_diff": outline_diff
            }

        # Highest severity wins
        severity = "high" if "major" in stale_levels else "medium"
        reason = "; ".join(reasons)

        return {
            "is_stale": True,
            "severity": severity,
            "reason": reason,
            "spec_diff": spec_diff,
            "outline_diff": outline_diff
        }

    def record_baseline_event(
        self,
        event_type: Literal["baseline.set", "baseline.unset", "baseline.lock", "baseline.unlock", "baseline.sync", "baseline.variant_change"],
        workspace_id: str,
        snapshot_id: str,
        new_state: Dict[str, Any],
        triggered_by: str,
        project_id: Optional[str] = None,
        variant_id: Optional[str] = None,
        previous_state: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        execution_id: Optional[str] = None
    ) -> str:
        """
        Record baseline change event for audit trail.

        Returns:
            Event ID
        """
        event_id = str(uuid.uuid4())
        now = datetime.utcnow()

        import json
        previous_state_json = json.dumps(previous_state) if previous_state else None
        new_state_json = json.dumps(new_state)

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO baseline_events (
                    id, event_type, workspace_id, project_id, snapshot_id, variant_id,
                    previous_state, new_state, reason, triggered_by, triggered_at, execution_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                event_id,
                event_type,
                workspace_id,
                project_id,
                snapshot_id,
                variant_id,
                previous_state_json,
                new_state_json,
                reason,
                triggered_by,
                now,
                execution_id
            ))
            conn.commit()

        return event_id

    def list_baseline_events(
        self,
        workspace_id: str,
        project_id: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        List baseline events for audit trail.

        Returns:
            List of event dicts, ordered by triggered_at DESC
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if project_id:
                cursor.execute("""
                    SELECT * FROM baseline_events
                    WHERE workspace_id = ? AND project_id = ?
                    ORDER BY triggered_at DESC
                    LIMIT ?
                """, (workspace_id, project_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM baseline_events
                    WHERE workspace_id = ? AND (project_id = ? OR project_id IS NULL)
                    ORDER BY triggered_at DESC
                    LIMIT ?
                """, (workspace_id, project_id, limit))

            rows = cursor.fetchall()

            import json
            events = []
            for row in rows:
                event = dict(row)
                # Parse JSON fields
                if event.get("previous_state"):
                    event["previous_state"] = json.loads(event["previous_state"])
                if event.get("new_state"):
                    event["new_state"] = json.loads(event["new_state"])
                events.append(event)

            return events
