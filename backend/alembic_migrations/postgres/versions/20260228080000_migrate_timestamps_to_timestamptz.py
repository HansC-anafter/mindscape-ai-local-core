"""Migrate all timestamp columns from naive to timezone-aware

Convert all 119 'timestamp without time zone' columns in the public schema
to 'timestamp with time zone'. Uses AT TIME ZONE 'UTC' to tell PostgreSQL
that existing naive values are UTC.

Revision ID: 20260228080000
Revises: 20260228000000
Create Date: 2026-02-28 08:50:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "20260228080000"
down_revision: Union[str, None] = "20260228000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# All tables and their naive timestamp columns, grouped by risk level.
# Data source: live query on 2026-02-28
# SELECT table_name, column_name FROM information_schema.columns
# WHERE data_type = 'timestamp without time zone' AND table_schema = 'public'

HIGH_RISK_TABLES = [
    # Core execution & scheduling — directly affect Duration calculation and timeline
    ("agent_executions", ["started_at", "completed_at"]),
    ("intents", ["created_at", "updated_at", "started_at", "completed_at", "due_date"]),
    ("background_routines", ["created_at", "last_run_at", "next_run_at", "updated_at"]),
    ("tool_calls", ["created_at", "started_at", "completed_at"]),
    ("runner_locks", ["created_at", "expires_at", "updated_at"]),
    ("workspaces", ["created_at", "updated_at"]),
    ("projects", ["created_at", "updated_at"]),
    ("project_phases", ["created_at"]),
    ("timeline_items", ["created_at"]),
    ("stage_results", ["created_at"]),
]

MEDIUM_RISK_TABLES = [
    # IG module
    ("ig_accounts_flat", ["created_at", "updated_at"]),
    ("ig_follow_edges", ["discovered_at"]),
    ("ig_posts", ["captured_at", "posted_at"]),
    ("ig_account_profiles", ["computed_at"]),
    ("ig_generated_personas", ["generated_at"]),
    # Tool system
    (
        "tool_connections",
        [
            "created_at",
            "last_discovery",
            "last_used_at",
            "last_validated_at",
            "updated_at",
        ],
    ),
    ("tool_registry", ["created_at", "updated_at"]),
    ("tool_slot_mappings", ["created_at", "updated_at"]),
    # AI role configs
    ("ai_role_configs", ["created_at", "last_used_at", "updated_at"]),
    ("ai_role_usage_records", ["used_at"]),
    ("role_capabilities", ["created_at"]),
    # Intent system
    ("intent_clusters", ["created_at", "updated_at"]),
    ("intent_logs", ["timestamp"]),
    ("intent_tags", ["confirmed_at", "created_at", "rejected_at", "updated_at"]),
]

LOW_RISK_TABLES = [
    # Embedding migrations
    (
        "embedding_migrations",
        ["completed_at", "created_at", "started_at", "updated_at"],
    ),
    ("embedding_migration_items", ["created_at", "updated_at"]),
    # Entity / Graph
    ("entities", ["created_at", "updated_at"]),
    ("entity_tags", ["created_at"]),
    ("graph_changelog", ["applied_at", "created_at"]),
    ("graph_edges", ["created_at"]),
    ("graph_node_entity_links", ["created_at"]),
    ("graph_node_intent_links", ["created_at"]),
    ("graph_node_playbook_links", ["created_at"]),
    ("graph_nodes", ["created_at", "updated_at"]),
    # Mind lens
    ("mind_lens_instances", ["created_at", "updated_at"]),
    ("mind_lens_active_nodes", ["created_at"]),
    ("mind_lens_profiles", ["created_at", "updated_at"]),
    ("mind_lens_schemas", ["created_at"]),
    ("mind_lens_workspace_bindings", ["created_at"]),
    ("lens_profile_nodes", ["updated_at"]),
    ("lens_receipts", ["created_at"]),
    ("lens_snapshots", ["created_at"]),
    ("lens_specs", ["created_at"]),
    # Mindscape
    ("mindscape_overlays", ["created_at", "updated_at"]),
    ("mindscape_personal", ["created_at", "updated_at"]),
    ("mind_events", ["timestamp"]),
    # Artifacts
    ("artifacts", ["created_at", "updated_at"]),
    ("artifact_registry", ["created_at", "updated_at"]),
    # Habits
    ("habit_candidates", ["created_at", "first_seen_at", "last_seen_at", "updated_at"]),
    ("habit_observations", ["created_at", "observed_at"]),
    ("habit_audit_logs", ["created_at"]),
    # Baseline & events
    ("baseline_events", ["triggered_at"]),
    ("web_generation_baselines", ["created_at", "updated_at"]),
    # Config & settings
    ("model_configs", ["created_at", "updated_at"]),
    ("model_providers", ["created_at", "updated_at"]),
    ("system_settings", ["updated_at"]),
    ("user_configs", ["updated_at"]),
    # Misc
    ("capability_ui_components", ["created_at"]),
    ("external_docs", ["created_at", "updated_at"]),
    ("installed_packs", ["installed_at"]),
    ("preview_votes", ["created_at"]),
    ("profiles", ["created_at", "updated_at"]),
    ("saved_views", ["created_at", "updated_at"]),
    ("task_feedback", ["created_at"]),
    ("task_preference", ["created_at", "updated_at"]),
    ("workspace_lens_overrides", ["updated_at"]),
]

ALL_TABLES = HIGH_RISK_TABLES + MEDIUM_RISK_TABLES + LOW_RISK_TABLES


def upgrade() -> None:
    """Convert all naive timestamp columns to timestamptz.

    Uses 'AT TIME ZONE 'UTC'' to inform PostgreSQL that existing values
    are UTC. This is a metadata-only change for most rows — PostgreSQL
    stores the same epoch internally, just adds timezone awareness.
    """
    for table_name, columns in ALL_TABLES:
        for col_name in columns:
            op.alter_column(
                table_name,
                col_name,
                type_=sa.DateTime(timezone=True),
                existing_type=sa.DateTime(),
                postgresql_using=f"{col_name} AT TIME ZONE 'UTC'",
            )


def downgrade() -> None:
    """Revert timestamptz columns back to naive timestamp.

    Converts back assuming UTC storage. Data precision is preserved.
    """
    for table_name, columns in ALL_TABLES:
        for col_name in columns:
            op.alter_column(
                table_name,
                col_name,
                type_=sa.DateTime(),
                existing_type=sa.DateTime(timezone=True),
                postgresql_using=f"{col_name} AT TIME ZONE 'UTC'",
            )
