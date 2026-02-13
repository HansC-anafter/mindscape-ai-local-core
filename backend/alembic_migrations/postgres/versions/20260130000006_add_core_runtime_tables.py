"""add_core_runtime_tables

Revision ID: 20260130000006
Revises: 20260130000005
Create Date: 2026-01-30 00:00:06.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "20260130000006"
down_revision = "20260130000005"
branch_labels = None
depends_on = None


def upgrade():
    # These tables are already introduced by 20260129000000_catchup_remaining.
    # Keep this revision as an explicit no-op to avoid duplicate table creation.
    return

    op.create_table(
        "commands",
        sa.Column("command_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("actor_id", sa.String(), nullable=False),
        sa.Column("source_surface", sa.String(), nullable=True),
        sa.Column("intent_code", sa.String(), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("requires_approval", sa.Boolean(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("parent_command_id", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("command_id"),
    )
    op.create_index("idx_commands_workspace", "commands", ["workspace_id"])
    op.create_index("idx_commands_thread", "commands", ["thread_id"])

    op.create_table(
        "conversation_threads",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("pinned_scope", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("message_count", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_conv_threads_workspace", "conversation_threads", ["workspace_id"]
    )
    op.create_index("idx_conv_threads_updated", "conversation_threads", ["updated_at"])

    op.create_table(
        "playbook_executions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("playbook_code", sa.String(), nullable=False),
        sa.Column("intent_instance_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=True),
        sa.Column("phase", sa.String(), nullable=True),
        sa.Column("last_checkpoint", sa.Text(), nullable=True),
        sa.Column("progress_log_path", sa.String(), nullable=True),
        sa.Column("feature_list_path", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_pb_exec_workspace", "playbook_executions", ["workspace_id"])
    op.create_index("idx_pb_exec_intent", "playbook_executions", ["intent_instance_id"])
    op.create_index("idx_pb_exec_thread", "playbook_executions", ["thread_id"])

    op.create_table(
        "lens_compositions",
        sa.Column("composition_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("lens_stack", sa.JSON(), nullable=True),
        sa.Column("fusion_strategy", sa.String(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("composition_id"),
    )
    op.create_index("idx_lens_comp_workspace", "lens_compositions", ["workspace_id"])

    op.create_table(
        "surface_events",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("source_surface", sa.String(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=True),
        sa.Column("actor_id", sa.String(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("command_id", sa.String(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("correlation_id", sa.String(), nullable=True),
        sa.Column("parent_event_id", sa.String(), nullable=True),
        sa.Column("execution_id", sa.String(), nullable=True),
        sa.Column("pack_id", sa.String(), nullable=True),
        sa.Column("card_id", sa.String(), nullable=True),
        sa.Column("scope", sa.String(), nullable=True),
        sa.Column("playbook_version", sa.String(), nullable=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index("idx_surface_events_workspace", "surface_events", ["workspace_id"])

    op.create_table(
        "user_playbook_meta",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("profile_id", sa.String(), nullable=False),
        sa.Column("playbook_code", sa.String(), nullable=False),
        sa.Column("favorite", sa.Integer(), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("custom_tags", sa.JSON(), nullable=True),
        sa.Column("user_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_upm_profile_playbook",
        "user_playbook_meta",
        ["profile_id", "playbook_code"],
        unique=True,
    )

    op.create_table(
        "thread_references",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workspace_id", sa.String(), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=True),
        sa.Column("uri", sa.String(), nullable=True),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("snippet", sa.Text(), nullable=True),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("pinned_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_thread_refs_thread", "thread_references", ["workspace_id", "thread_id"]
    )


def downgrade():
    # No-op downgrade; tables belong to earlier schema baseline revisions.
    return

    op.drop_index("idx_thread_refs_thread", table_name="thread_references")
    op.drop_table("thread_references")
    op.drop_index("idx_upm_profile_playbook", table_name="user_playbook_meta")
    op.drop_table("user_playbook_meta")
    op.drop_index("idx_surface_events_workspace", table_name="surface_events")
    op.drop_table("surface_events")
    op.drop_index("idx_lens_comp_workspace", table_name="lens_compositions")
    op.drop_table("lens_compositions")
    op.drop_index("idx_pb_exec_thread", table_name="playbook_executions")
    op.drop_index("idx_pb_exec_intent", table_name="playbook_executions")
    op.drop_index("idx_pb_exec_workspace", table_name="playbook_executions")
    op.drop_table("playbook_executions")
    op.drop_index("idx_conv_threads_updated", table_name="conversation_threads")
    op.drop_index("idx_conv_threads_workspace", table_name="conversation_threads")
    op.drop_table("conversation_threads")
    op.drop_index("idx_commands_thread", table_name="commands")
    op.drop_index("idx_commands_workspace", table_name="commands")
    op.drop_table("commands")
