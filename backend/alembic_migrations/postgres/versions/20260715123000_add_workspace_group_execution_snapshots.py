"""Add immutable Workspace Group execution snapshots.

Revision ID: 20260715123000
Revises: 20260715120000
Create Date: 2026-07-15 12:30:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260715123000"
down_revision = "20260715120000"
branch_labels = None
depends_on = None


def _ensure_snapshot_reference(
    *,
    table_name: str,
    constraint_name: str,
    index_name: str,
) -> None:
    """Converge bootstrap-created TEXT columns into the canonical FK seam."""
    column_name = "workspace_group_snapshot_id"
    op.execute(
        f"ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS "
        f"{column_name} VARCHAR(64)"
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM {table_name}
                WHERE length({column_name}) > 64
            ) THEN
                RAISE EXCEPTION
                    '{table_name}.{column_name} contains values longer than 64 characters';
            END IF;
        END;
        $$
        """
    )
    op.execute(
        f"ALTER TABLE {table_name} ALTER COLUMN {column_name} "
        "TYPE VARCHAR(64) USING workspace_group_snapshot_id::VARCHAR(64)"
    )
    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1
                FROM pg_constraint
                WHERE conname = '{constraint_name}'
                  AND conrelid = '{table_name}'::regclass
            ) THEN
                ALTER TABLE {table_name}
                ADD CONSTRAINT {constraint_name}
                FOREIGN KEY ({column_name})
                REFERENCES workspace_group_topology_snapshots(id)
                ON DELETE RESTRICT;
            END IF;
        END;
        $$
        """
    )
    op.execute(
        f"CREATE INDEX IF NOT EXISTS {index_name} "
        f"ON {table_name} ({column_name})"
    )


def upgrade() -> None:
    op.create_table(
        "workspace_group_topology_snapshots",
        sa.Column("id", sa.String(64), nullable=False),
        sa.Column("group_id", sa.String(64), nullable=False),
        sa.Column("group_revision", sa.BigInteger(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_by_user_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["group_id"],
            ["workspace_group_definitions.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "group_id",
            "group_revision",
            "content_hash",
            name="uq_workspace_group_topology_snapshot_content",
        ),
    )
    op.create_index(
        "idx_workspace_group_topology_snapshots_group_revision",
        "workspace_group_topology_snapshots",
        ["group_id", "group_revision"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_workspace_group_snapshot_update()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'workspace_group_topology_snapshots are immutable';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER workspace_group_topology_snapshot_immutable
        BEFORE UPDATE ON workspace_group_topology_snapshots
        FOR EACH ROW EXECUTE FUNCTION reject_workspace_group_snapshot_update()
        """
    )
    _ensure_snapshot_reference(
        table_name="meeting_sessions",
        constraint_name="fk_meeting_sessions_workspace_group_snapshot",
        index_name="idx_meeting_sessions_workspace_group_snapshot",
    )
    _ensure_snapshot_reference(
        table_name="task_irs",
        constraint_name="fk_task_irs_workspace_group_snapshot",
        index_name="idx_task_irs_workspace_group_snapshot",
    )


def downgrade() -> None:
    op.drop_index("idx_task_irs_workspace_group_snapshot", table_name="task_irs")
    op.drop_constraint(
        "fk_task_irs_workspace_group_snapshot", "task_irs", type_="foreignkey"
    )
    op.drop_column("task_irs", "workspace_group_snapshot_id")
    op.drop_index(
        "idx_meeting_sessions_workspace_group_snapshot",
        table_name="meeting_sessions",
    )
    op.drop_constraint(
        "fk_meeting_sessions_workspace_group_snapshot",
        "meeting_sessions",
        type_="foreignkey",
    )
    op.drop_column("meeting_sessions", "workspace_group_snapshot_id")
    op.drop_index(
        "idx_workspace_group_topology_snapshots_group_revision",
        table_name="workspace_group_topology_snapshots",
    )
    op.drop_table("workspace_group_topology_snapshots")
    op.execute("DROP FUNCTION reject_workspace_group_snapshot_update()")
