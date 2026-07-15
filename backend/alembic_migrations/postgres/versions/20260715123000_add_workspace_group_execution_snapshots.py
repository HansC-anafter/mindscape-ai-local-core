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
    op.add_column(
        "meeting_sessions",
        sa.Column("workspace_group_snapshot_id", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_meeting_sessions_workspace_group_snapshot",
        "meeting_sessions",
        "workspace_group_topology_snapshots",
        ["workspace_group_snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_meeting_sessions_workspace_group_snapshot",
        "meeting_sessions",
        ["workspace_group_snapshot_id"],
    )
    op.add_column(
        "task_irs",
        sa.Column("workspace_group_snapshot_id", sa.String(64), nullable=True),
    )
    op.create_foreign_key(
        "fk_task_irs_workspace_group_snapshot",
        "task_irs",
        "workspace_group_topology_snapshots",
        ["workspace_group_snapshot_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "idx_task_irs_workspace_group_snapshot",
        "task_irs",
        ["workspace_group_snapshot_id"],
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
