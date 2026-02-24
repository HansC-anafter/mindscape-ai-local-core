"""
GoalSet store for L2 Bridge governance goals.

PostgreSQL store for persisting GoalSet and GoalClause models,
providing the G = {g1, g2, ...} target set for L3 Progress scoring.
"""

import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from sqlalchemy import text

from backend.app.services.stores.postgres_base import PostgresStoreBase
from backend.app.models.goal_set import GoalSet, GoalClause, GoalCategory

logger = logging.getLogger(__name__)


TABLE_DDL = """
CREATE TABLE IF NOT EXISTS goal_sets (
    id               TEXT PRIMARY KEY,
    workspace_id     TEXT NOT NULL,
    project_id       TEXT,
    version          INTEGER NOT NULL DEFAULT 1,
    is_active        BOOLEAN NOT NULL DEFAULT true,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata         JSONB DEFAULT '{}'
);
"""

CLAUSES_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS goal_clauses (
    id               TEXT PRIMARY KEY,
    goal_set_id      TEXT NOT NULL REFERENCES goal_sets(id) ON DELETE CASCADE,
    category         TEXT NOT NULL,
    text             TEXT NOT NULL,
    weight           FLOAT NOT NULL DEFAULT 1.0,
    evidence_required BOOLEAN NOT NULL DEFAULT false,
    embedding        JSONB,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    metadata         JSONB DEFAULT '{}'
);
"""

INDEX_DDL = [
    "CREATE INDEX IF NOT EXISTS idx_goal_sets_ws_project ON goal_sets(workspace_id, project_id)",
    "CREATE INDEX IF NOT EXISTS idx_goal_clauses_set ON goal_clauses(goal_set_id)",
]


class GoalSetStore(PostgresStoreBase):
    """Store for GoalSet + GoalClause persistence (Postgres)."""

    _table_ensured = False

    def __init__(self, db_role: str = "core"):
        super().__init__(db_role=db_role)
        if not GoalSetStore._table_ensured:
            self.ensure_table()
            GoalSetStore._table_ensured = True

    def ensure_table(self) -> None:
        """Create tables if they do not exist."""
        with self.transaction() as conn:
            conn.execute(text(TABLE_DDL))
            conn.execute(text(CLAUSES_TABLE_DDL))
            for idx in INDEX_DDL:
                conn.execute(text(idx))
        logger.info("goal_sets + goal_clauses tables ensured")

    # ============== Write ==============

    def create(self, goal_set: GoalSet) -> GoalSet:
        """Insert a GoalSet with all its clauses."""
        with self.transaction() as conn:
            conn.execute(
                text(
                    """
                    INSERT INTO goal_sets (id, workspace_id, project_id,
                        version, is_active, created_at, updated_at, metadata)
                    VALUES (:id, :workspace_id, :project_id,
                        :version, :is_active, :created_at, :updated_at, :metadata)
                """
                ),
                {
                    "id": goal_set.id,
                    "workspace_id": goal_set.workspace_id,
                    "project_id": goal_set.project_id,
                    "version": goal_set.version,
                    "is_active": goal_set.is_active,
                    "created_at": goal_set.created_at,
                    "updated_at": goal_set.updated_at,
                    "metadata": self.serialize_json(goal_set.metadata),
                },
            )
            for clause in goal_set.clauses:
                conn.execute(
                    text(
                        """
                        INSERT INTO goal_clauses (id, goal_set_id, category,
                            text, weight, evidence_required, embedding,
                            created_at, updated_at, metadata)
                        VALUES (:id, :goal_set_id, :category,
                            :text, :weight, :evidence_required, :embedding,
                            :created_at, :updated_at, :metadata)
                    """
                    ),
                    {
                        "id": clause.id,
                        "goal_set_id": goal_set.id,
                        "category": (
                            clause.category.value
                            if hasattr(clause.category, "value")
                            else str(clause.category)
                        ),
                        "text": clause.text,
                        "weight": clause.weight,
                        "evidence_required": clause.evidence_required,
                        "embedding": self.serialize_json(clause.embedding),
                        "created_at": clause.created_at,
                        "updated_at": clause.updated_at,
                        "metadata": self.serialize_json(clause.metadata),
                    },
                )
        return goal_set

    # ============== Read ==============

    def get_by_id(self, goal_set_id: str) -> Optional[GoalSet]:
        """Get a GoalSet by ID with all clauses."""
        with self.get_connection() as conn:
            row = conn.execute(
                text("SELECT * FROM goal_sets WHERE id = :id"),
                {"id": goal_set_id},
            ).fetchone()
            if not row:
                return None
            return self._row_to_goal_set(conn, row)

    def list_by_project(
        self, workspace_id: str, project_id: str, limit: int = 20
    ) -> List[GoalSet]:
        """List GoalSets for a project, newest first."""
        with self.get_connection() as conn:
            rows = conn.execute(
                text(
                    """
                    SELECT * FROM goal_sets
                    WHERE workspace_id = :ws AND project_id = :pid
                    ORDER BY created_at DESC LIMIT :lim
                """
                ),
                {"ws": workspace_id, "pid": project_id, "lim": limit},
            ).fetchall()
            return [self._row_to_goal_set(conn, r) for r in rows]

    # ============== Internal ==============

    def _row_to_goal_set(self, conn, row) -> GoalSet:
        """Convert a database row + clauses to GoalSet."""
        data = row._mapping if hasattr(row, "_mapping") else row
        clauses_rows = conn.execute(
            text("SELECT * FROM goal_clauses WHERE goal_set_id = :gid"),
            {"gid": data["id"]},
        ).fetchall()
        clauses = []
        for cr in clauses_rows:
            cd = cr._mapping if hasattr(cr, "_mapping") else cr
            cat_raw = cd.get("category", "what")
            try:
                cat = GoalCategory(cat_raw)
            except Exception:
                cat = GoalCategory.WHAT
            created = cd.get("created_at")
            if created and not isinstance(created, datetime):
                created = datetime.fromisoformat(str(created))
            updated = cd.get("updated_at")
            if updated and not isinstance(updated, datetime):
                updated = datetime.fromisoformat(str(updated))
            clauses.append(
                GoalClause(
                    id=cd["id"],
                    category=cat,
                    text=cd["text"],
                    weight=cd.get("weight", 1.0),
                    evidence_required=cd.get("evidence_required", False),
                    embedding=self.deserialize_json(cd.get("embedding"), None),
                    metadata=self.deserialize_json(cd.get("metadata"), {}),
                    created_at=created or datetime.now(),
                    updated_at=updated or datetime.now(),
                )
            )

        gs_created = data["created_at"]
        if not isinstance(gs_created, datetime):
            gs_created = datetime.fromisoformat(str(gs_created))
        gs_updated = data.get("updated_at")
        if gs_updated and not isinstance(gs_updated, datetime):
            gs_updated = datetime.fromisoformat(str(gs_updated))

        return GoalSet(
            id=data["id"],
            workspace_id=data["workspace_id"],
            project_id=data.get("project_id"),
            clauses=clauses,
            version=data.get("version", 1),
            is_active=data.get("is_active", True),
            metadata=self.deserialize_json(data.get("metadata"), {}),
            created_at=gs_created,
            updated_at=gs_updated or gs_created,
        )
