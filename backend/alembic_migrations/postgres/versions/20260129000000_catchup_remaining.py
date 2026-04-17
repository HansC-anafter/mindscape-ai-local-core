"""catchup_remaining

Revision ID: 20260129000000
Revises: 20260128000000
Create Date: 2026-01-29 09:00:00.000000

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "20260129000000"
down_revision = "20260129000001"
branch_labels = None
depends_on = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return any(
        index.get("name") == index_name for index in inspector.get_indexes(table_name)
    )


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # 1. Commands
    if not _has_table(inspector, "commands"):
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
        inspector = sa.inspect(bind)
    if _has_table(inspector, "commands") and not _has_index(
        inspector, "commands", "idx_commands_workspace"
    ):
        op.create_index("idx_commands_workspace", "commands", ["workspace_id"])
        inspector = sa.inspect(bind)
    if _has_table(inspector, "commands") and not _has_index(
        inspector, "commands", "idx_commands_thread"
    ):
        op.create_index("idx_commands_thread", "commands", ["thread_id"])
        inspector = sa.inspect(bind)

    # 2. Conversation Threads
    if not _has_table(inspector, "conversation_threads"):
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
        inspector = sa.inspect(bind)
    if _has_table(inspector, "conversation_threads") and not _has_index(
        inspector, "conversation_threads", "idx_conv_threads_workspace"
    ):
        op.create_index(
            "idx_conv_threads_workspace", "conversation_threads", ["workspace_id"]
        )
        inspector = sa.inspect(bind)
    if _has_table(inspector, "conversation_threads") and not _has_index(
        inspector, "conversation_threads", "idx_conv_threads_updated"
    ):
        op.create_index(
            "idx_conv_threads_updated", "conversation_threads", ["updated_at"]
        )
        inspector = sa.inspect(bind)

    # 3. Playbook Executions
    if not _has_table(inspector, "playbook_executions"):
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
        inspector = sa.inspect(bind)
    if _has_table(inspector, "playbook_executions") and not _has_index(
        inspector, "playbook_executions", "idx_pb_exec_workspace"
    ):
        op.create_index("idx_pb_exec_workspace", "playbook_executions", ["workspace_id"])
        inspector = sa.inspect(bind)
    if _has_table(inspector, "playbook_executions") and not _has_index(
        inspector, "playbook_executions", "idx_pb_exec_intent"
    ):
        op.create_index(
            "idx_pb_exec_intent", "playbook_executions", ["intent_instance_id"]
        )
        inspector = sa.inspect(bind)
    if _has_table(inspector, "playbook_executions") and not _has_index(
        inspector, "playbook_executions", "idx_pb_exec_thread"
    ):
        op.create_index("idx_pb_exec_thread", "playbook_executions", ["thread_id"])
        inspector = sa.inspect(bind)

    # 4. Lens Compositions
    if not _has_table(inspector, "lens_compositions"):
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
        inspector = sa.inspect(bind)
    if _has_table(inspector, "lens_compositions") and not _has_index(
        inspector, "lens_compositions", "idx_lens_comp_workspace"
    ):
        op.create_index("idx_lens_comp_workspace", "lens_compositions", ["workspace_id"])
        inspector = sa.inspect(bind)

    # 5. Surface Events
    if not _has_table(inspector, "surface_events"):
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
        inspector = sa.inspect(bind)
    if _has_table(inspector, "surface_events") and not _has_index(
        inspector, "surface_events", "idx_surface_events_workspace"
    ):
        op.create_index("idx_surface_events_workspace", "surface_events", ["workspace_id"])
        inspector = sa.inspect(bind)

    # 6. User Playbook Meta
    if not _has_table(inspector, "user_playbook_meta"):
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
        inspector = sa.inspect(bind)
    if _has_table(inspector, "user_playbook_meta") and not _has_index(
        inspector, "user_playbook_meta", "idx_upm_profile_playbook"
    ):
        op.create_index(
            "idx_upm_profile_playbook",
            "user_playbook_meta",
            ["profile_id", "playbook_code"],
            unique=True,
        )
        inspector = sa.inspect(bind)

    # 7. Thread References
    if not _has_table(inspector, "thread_references"):
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
        inspector = sa.inspect(bind)
    if _has_table(inspector, "thread_references") and not _has_index(
        inspector, "thread_references", "idx_thread_refs_thread"
    ):
        op.create_index(
            "idx_thread_refs_thread", "thread_references", ["workspace_id", "thread_id"]
        )


def downgrade():
    op.drop_table("thread_references")
    op.drop_table("user_playbook_meta")
    op.drop_table("surface_events")
    op.drop_table("lens_compositions")
    op.drop_table("playbook_executions")
    op.drop_table("conversation_threads")
    op.drop_table("commands")
