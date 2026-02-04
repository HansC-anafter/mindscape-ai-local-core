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
    # --- Intents ---
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
    op.create_index("ix_intents_profile", "intents", ["profile_id"])
    op.create_index("ix_intents_status", "intents", ["status"])
    op.create_index("ix_intents_parent", "intents", ["parent_intent_id"])

    # --- Agent Executions ---
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
    op.create_index("ix_agent_executions_profile", "agent_executions", ["profile_id"])
    op.create_index("ix_agent_executions_status", "agent_executions", ["status"])
    op.create_index("ix_agent_executions_start", "agent_executions", ["started_at"])

    # --- Mind Events ---
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
    op.create_index("ix_mind_events_profile", "mind_events", ["profile_id"])
    op.create_index("ix_mind_events_time", "mind_events", ["timestamp"])
    op.create_index("ix_mind_events_thread", "mind_events", ["thread_id"])
    op.create_index("ix_mind_events_type", "mind_events", ["event_type"])
    op.create_index("ix_mind_events_project", "mind_events", ["project_id"])
    op.create_index("ix_mind_events_workspace", "mind_events", ["workspace_id"])


def downgrade():
    op.drop_table("mind_events")
    op.drop_table("agent_executions")
    op.drop_table("intents")
