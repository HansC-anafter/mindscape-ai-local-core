"""Add runtime auxiliary tables (tool calls, stage results, intent tags, etc.)

Revision ID: 20260130000008
Revises: 20260130000007
Create Date: 2026-01-30 00:00:08.000000
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260130000008"
down_revision = "20260130000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- Tool Calls ---
    op.create_table(
        "tool_calls",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=True),
        sa.Column("tool_name", sa.String(length=255), nullable=False),
        sa.Column("tool_id", sa.String(length=255), nullable=True),
        sa.Column("parameters", sa.Text(), nullable=False),
        sa.Column("response", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("factory_cluster", sa.String(length=255), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_tool_calls_execution", "tool_calls", ["execution_id"])
    op.create_index("idx_tool_calls_step", "tool_calls", ["step_id"])
    op.create_index("idx_tool_calls_tool", "tool_calls", ["tool_name"])
    op.create_index("idx_tool_calls_cluster", "tool_calls", ["factory_cluster"])

    # --- Stage Results ---
    op.create_table(
        "stage_results",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=False),
        sa.Column("step_id", sa.String(length=255), nullable=True),
        sa.Column("stage_name", sa.String(length=255), nullable=False),
        sa.Column("result_type", sa.String(length=50), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("preview", sa.Text(), nullable=True),
        sa.Column("requires_review", sa.Boolean(), server_default=sa.text("FALSE"), nullable=False),
        sa.Column("review_status", sa.String(length=50), nullable=True),
        sa.Column("artifact_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_stage_results_execution", "stage_results", ["execution_id"])
    op.create_index("idx_stage_results_step", "stage_results", ["step_id"])
    op.create_index("idx_stage_results_review", "stage_results", ["requires_review", "review_status"])
    op.create_index("idx_stage_results_artifact", "stage_results", ["artifact_id"])

    # --- Intent Tags ---
    op.create_table(
        "intent_tags",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("status", sa.String(length=32), server_default="candidate", nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("execution_id", sa.String(length=36), nullable=True),
        sa.Column("playbook_code", sa.String(length=255), nullable=True),
        sa.Column("message_id", sa.String(length=255), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.Column("rejected_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("idx_intent_tags_workspace", "intent_tags", ["workspace_id"])
    op.create_index("idx_intent_tags_profile", "intent_tags", ["profile_id"])
    op.create_index("idx_intent_tags_status", "intent_tags", ["status"])
    op.create_index("idx_intent_tags_execution", "intent_tags", ["execution_id"])
    op.create_index(
        "idx_intent_tags_workspace_status", "intent_tags", ["workspace_id", "status"]
    )

    # --- Intent Clusters ---
    op.create_table(
        "intent_clusters",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("embedding", sa.Text(), nullable=True),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("profile_id", sa.String(length=36), nullable=True),
        sa.Column("intent_card_ids", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_intent_clusters_workspace", "intent_clusters", ["workspace_id"])
    op.create_index("idx_intent_clusters_profile", "intent_clusters", ["profile_id"])

    # --- Tool Slot Mappings ---
    op.create_table(
        "tool_slot_mappings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("slot", sa.String(length=255), nullable=False),
        sa.Column("tool_id", sa.String(length=255), nullable=False),
        sa.Column("priority", sa.Integer(), server_default="0", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("TRUE"), nullable=False),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "project_id", "slot", name="uq_tool_slot_mapping"),
    )
    op.create_index(
        "idx_tool_slot_mappings_workspace_slot",
        "tool_slot_mappings",
        ["workspace_id", "slot", "enabled"],
    )
    op.create_index(
        "idx_tool_slot_mappings_project_slot",
        "tool_slot_mappings",
        ["project_id", "slot", "enabled"],
    )

    # --- Embedding Migrations ---
    op.create_table(
        "embedding_migrations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_model", sa.String(length=255), nullable=False),
        sa.Column("target_model", sa.String(length=255), nullable=False),
        sa.Column("source_provider", sa.String(length=255), nullable=False),
        sa.Column("target_provider", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=True),
        sa.Column("intent_id", sa.String(length=36), nullable=True),
        sa.Column("scope", sa.String(length=255), nullable=True),
        sa.Column("strategy", sa.String(length=50), nullable=False),
        sa.Column("total_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("processed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("failed_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_embedding_migrations_user_id", "embedding_migrations", ["user_id"]
    )
    op.create_index(
        "idx_embedding_migrations_status", "embedding_migrations", ["status"]
    )

    op.create_table(
        "embedding_migration_items",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("migration_id", sa.String(length=36), nullable=False),
        sa.Column("source_embedding_id", sa.String(length=255), nullable=False),
        sa.Column("target_embedding_id", sa.String(length=255), nullable=True),
        sa.Column("source_table", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["migration_id"], ["embedding_migrations.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "idx_embedding_migration_items_migration_id",
        "embedding_migration_items",
        ["migration_id"],
    )
    op.create_index(
        "idx_embedding_migration_items_status",
        "embedding_migration_items",
        ["status"],
    )

    # --- Web Generation Baselines ---
    op.create_table(
        "web_generation_baselines",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("snapshot_id", sa.String(length=255), nullable=False),
        sa.Column("variant_id", sa.String(length=255), nullable=True),
        sa.Column("lock_mode", sa.String(length=20), server_default="advisory", nullable=False),
        sa.Column("bound_spec_version", sa.String(length=100), nullable=True),
        sa.Column("bound_outline_version", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("created_by", sa.String(length=255), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "lock_mode IN ('locked', 'advisory')", name="ck_baseline_lock_mode"
        ),
        sa.UniqueConstraint("workspace_id", "project_id", name="uq_baseline_workspace_project"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_baseline_workspace", "web_generation_baselines", ["workspace_id"]
    )
    op.create_index(
        "idx_baseline_project", "web_generation_baselines", ["project_id"]
    )
    op.create_index(
        "idx_baseline_snapshot", "web_generation_baselines", ["snapshot_id"]
    )

    op.create_table(
        "baseline_events",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=50), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("snapshot_id", sa.String(length=255), nullable=False),
        sa.Column("variant_id", sa.String(length=255), nullable=True),
        sa.Column("previous_state", sa.Text(), nullable=True),
        sa.Column("new_state", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("triggered_by", sa.String(length=255), nullable=False),
        sa.Column("triggered_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("execution_id", sa.String(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_baseline_events_lookup",
        "baseline_events",
        ["workspace_id", "project_id", "triggered_at"],
    )
    op.create_index(
        "idx_baseline_events_snapshot",
        "baseline_events",
        ["snapshot_id", "triggered_at"],
    )
    op.create_index(
        "idx_baseline_events_type",
        "baseline_events",
        ["event_type", "triggered_at"],
    )


def downgrade() -> None:
    op.drop_index("idx_baseline_events_type", table_name="baseline_events")
    op.drop_index("idx_baseline_events_snapshot", table_name="baseline_events")
    op.drop_index("idx_baseline_events_lookup", table_name="baseline_events")
    op.drop_table("baseline_events")

    op.drop_index("idx_baseline_snapshot", table_name="web_generation_baselines")
    op.drop_index("idx_baseline_project", table_name="web_generation_baselines")
    op.drop_index("idx_baseline_workspace", table_name="web_generation_baselines")
    op.drop_table("web_generation_baselines")

    op.drop_index("idx_embedding_migration_items_status", table_name="embedding_migration_items")
    op.drop_index("idx_embedding_migration_items_migration_id", table_name="embedding_migration_items")
    op.drop_table("embedding_migration_items")

    op.drop_index("idx_embedding_migrations_status", table_name="embedding_migrations")
    op.drop_index("idx_embedding_migrations_user_id", table_name="embedding_migrations")
    op.drop_table("embedding_migrations")

    op.drop_index("idx_tool_slot_mappings_project_slot", table_name="tool_slot_mappings")
    op.drop_index("idx_tool_slot_mappings_workspace_slot", table_name="tool_slot_mappings")
    op.drop_table("tool_slot_mappings")

    op.drop_index("idx_intent_clusters_profile", table_name="intent_clusters")
    op.drop_index("idx_intent_clusters_workspace", table_name="intent_clusters")
    op.drop_table("intent_clusters")

    op.drop_index("idx_intent_tags_workspace_status", table_name="intent_tags")
    op.drop_index("idx_intent_tags_execution", table_name="intent_tags")
    op.drop_index("idx_intent_tags_status", table_name="intent_tags")
    op.drop_index("idx_intent_tags_profile", table_name="intent_tags")
    op.drop_index("idx_intent_tags_workspace", table_name="intent_tags")
    op.drop_table("intent_tags")

    op.drop_index("idx_stage_results_artifact", table_name="stage_results")
    op.drop_index("idx_stage_results_review", table_name="stage_results")
    op.drop_index("idx_stage_results_step", table_name="stage_results")
    op.drop_index("idx_stage_results_execution", table_name="stage_results")
    op.drop_table("stage_results")

    op.drop_index("idx_tool_calls_cluster", table_name="tool_calls")
    op.drop_index("idx_tool_calls_tool", table_name="tool_calls")
    op.drop_index("idx_tool_calls_step", table_name="tool_calls")
    op.drop_index("idx_tool_calls_execution", table_name="tool_calls")
    op.drop_table("tool_calls")
