"""Core Operations (Intents, Executions, Events)

Revision ID: 20260128000000
Revises: 20260127000000
Create Date: 2026-01-28 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260128000000"
down_revision = "20260127000000"
branch_labels = None
depends_on = None


def upgrade():
    inspector = sa.inspect(op.get_bind())

    # --- Intents ---
    if not inspector.has_table("intents"):
        op.create_table(
            "intents",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("profile_id", sa.String(length=36), nullable=False),
            sa.Column("title", sa.Text(), nullable=False),
            sa.Column("description", sa.Text(), nullable=False),
            sa.Column(
                "status", sa.String(length=32), server_default="active", nullable=False
            ),
            sa.Column(
                "priority", sa.String(length=32), server_default="medium", nullable=False
            ),
            sa.Column("tags", sa.Text(), nullable=True),  # JSON list
            sa.Column("storyline_tags", sa.Text(), nullable=True),  # JSON list
            sa.Column("category", sa.String(length=128), nullable=True),
            sa.Column(
                "progress_percentage", sa.Integer(), server_default="0", nullable=False
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("due_date", sa.DateTime(), nullable=True),
            sa.Column("parent_intent_id", sa.String(length=36), nullable=True),
            sa.Column("child_intent_ids", sa.Text(), nullable=True),  # JSON list
            sa.Column("metadata", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(
                ["parent_intent_id"], ["intents.id"], ondelete="SET NULL"
            ),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_intents_profile ON intents (profile_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intents_status ON intents (status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_intents_parent ON intents (parent_intent_id)")

    # --- Agent Executions ---
    if not inspector.has_table("agent_executions"):
        op.create_table(
            "agent_executions",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("profile_id", sa.String(length=36), nullable=False),
            sa.Column("agent_type", sa.String(length=64), nullable=False),
            sa.Column("task", sa.Text(), nullable=False),
            sa.Column("intent_ids", sa.Text(), nullable=True),  # JSON list
            sa.Column(
                "status", sa.String(length=32), server_default="pending", nullable=False
            ),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.Column("duration_seconds", sa.Float(), nullable=True),
            sa.Column("output", sa.Text(), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("used_profile", sa.Text(), nullable=True),  # JSON
            sa.Column("used_intents", sa.Text(), nullable=True),  # JSON
            sa.Column("metadata", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_executions_profile ON agent_executions (profile_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_executions_status ON agent_executions (status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_agent_executions_start ON agent_executions (started_at)"
    )

    # --- Mind Events ---
    if not inspector.has_table("mind_events"):
        op.create_table(
            "mind_events",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column(
                "timestamp",
                sa.DateTime(),
                server_default=sa.text("CURRENT_TIMESTAMP"),
                nullable=False,
            ),
            sa.Column("actor", sa.String(length=32), nullable=False),
            sa.Column("channel", sa.String(length=64), nullable=False),
            sa.Column("profile_id", sa.String(length=36), nullable=False),
            sa.Column("project_id", sa.String(length=36), nullable=True),
            sa.Column("workspace_id", sa.String(length=36), nullable=True),
            sa.Column("thread_id", sa.String(length=128), nullable=True),
            sa.Column("event_type", sa.String(length=64), nullable=False),
            sa.Column("payload", sa.Text(), nullable=True),  # JSON
            sa.Column("entity_ids", sa.Text(), nullable=True),  # JSON list
            sa.Column("metadata", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="SET NULL"),
            sa.ForeignKeyConstraint(
                ["workspace_id"], ["workspaces.id"], ondelete="SET NULL"
            ),
        )
    op.execute("CREATE INDEX IF NOT EXISTS ix_mind_events_profile ON mind_events (profile_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mind_events_time ON mind_events (timestamp)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mind_events_thread ON mind_events (thread_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mind_events_type ON mind_events (event_type)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mind_events_project ON mind_events (project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mind_events_workspace ON mind_events (workspace_id)")


def downgrade():
    op.drop_table("mind_events")
    op.drop_table("agent_executions")
    op.drop_table("intents")
