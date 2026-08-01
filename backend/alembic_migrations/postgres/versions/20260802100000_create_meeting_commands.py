"""Create the durable Meeting Workbench command ledger."""

from alembic import op
import sqlalchemy as sa


revision = "20260802100000"
down_revision = "20260726100000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "meeting_commands",
        sa.Column("command_id", sa.Text(), primary_key=True),
        sa.Column("workspace_id", sa.Text(), nullable=False),
        sa.Column("meeting_id", sa.Text(), nullable=False),
        sa.Column("thread_id", sa.Text()),
        sa.Column("client_draft_id", sa.Text()),
        sa.Column("origin_surface", sa.Text(), nullable=False),
        sa.Column("actor", sa.Text(), nullable=False),
        sa.Column("intent_text", sa.Text(), nullable=False),
        sa.Column("context_objects", sa.JSON(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("requested_action", sa.JSON(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("expected_outputs", sa.JSON(), server_default=sa.text("'[]'::jsonb")),
        sa.Column(
            "write_mode",
            sa.Text(),
            nullable=False,
            server_default="recommendation_only",
        ),
        sa.Column("status", sa.Text(), nullable=False, server_default="accepted"),
        sa.Column("accepted_task_id", sa.Text()),
        sa.Column("metadata", sa.JSON(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index(
        "idx_meeting_commands_ws_meeting",
        "meeting_commands",
        ["workspace_id", "meeting_id", "created_at"],
    )
    op.create_index(
        "idx_meeting_commands_ws_thread",
        "meeting_commands",
        ["workspace_id", "thread_id"],
    )
    op.create_index(
        "idx_meeting_commands_client_draft",
        "meeting_commands",
        ["workspace_id", "meeting_id", "client_draft_id"],
    )


def downgrade():
    op.drop_index("idx_meeting_commands_client_draft", table_name="meeting_commands")
    op.drop_index("idx_meeting_commands_ws_thread", table_name="meeting_commands")
    op.drop_index("idx_meeting_commands_ws_meeting", table_name="meeting_commands")
    op.drop_table("meeting_commands")
