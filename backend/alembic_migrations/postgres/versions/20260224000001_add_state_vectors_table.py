"""Add state_vectors table for L3 convergence engine

Revision ID: 20260224000001
Revises: 20260224000000
Create Date: 2026-02-24
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260224000001"
down_revision: Union[str, Sequence[str]] = "20260224000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use IF NOT EXISTS because state_vector_store may have already ensured
    # this table in local/dev environments before migration runs.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS state_vectors (
            id                  TEXT PRIMARY KEY,
            meeting_session_id  TEXT NOT NULL,
            workspace_id        TEXT NOT NULL,
            project_id          TEXT,
            progress            REAL NOT NULL DEFAULT 0,
            evidence            REAL NOT NULL DEFAULT 0,
            risk                REAL NOT NULL DEFAULT 0,
            drift               REAL NOT NULL DEFAULT 0,
            lyapunov_v          REAL NOT NULL DEFAULT 0,
            mode                TEXT NOT NULL DEFAULT 'explore',
            metadata            JSONB DEFAULT '{}',
            created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        """
    )

    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sv_ws_created
        ON state_vectors(workspace_id, created_at DESC);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_sv_session
        ON state_vectors(meeting_session_id);
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS state_vectors;")
