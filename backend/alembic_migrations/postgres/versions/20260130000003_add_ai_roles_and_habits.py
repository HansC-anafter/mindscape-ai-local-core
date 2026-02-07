"""Add AI Roles + Habits Tables

Revision ID: 20260130000003
Revises: 20260130000002
Create Date: 2026-01-30 00:00:03.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260130000003"
down_revision = "20260130000002"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "ai_role_configs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("agent_type", sa.String(length=64), nullable=False),
        sa.Column(
            "icon", sa.String(length=32), server_default="bot", nullable=False
        ),
        sa.Column("playbooks", sa.Text(), nullable=True),
        sa.Column("suggested_tasks", sa.Text(), nullable=True),
        sa.Column("tools", sa.Text(), nullable=True),
        sa.Column("mindscape_profile_override", sa.Text(), nullable=True),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column(
            "is_enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "is_custom",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
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
        sa.Column("x_platform", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_ai_role_configs_profile", "ai_role_configs", ["profile_id"])
    op.create_index("ix_ai_role_configs_enabled", "ai_role_configs", ["is_enabled"])

    op.create_table(
        "ai_role_usage_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("execution_id", sa.String(length=64), nullable=False),
        sa.Column("task", sa.Text(), nullable=False),
        sa.Column(
            "used_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["role_id"], ["ai_role_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_ai_role_usage_profile", "ai_role_usage_records", ["profile_id"]
    )

    op.create_table(
        "role_capabilities",
        sa.Column("role_id", sa.String(length=64), nullable=False),
        sa.Column("capability_id", sa.String(length=128), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("blurb", sa.Text(), nullable=False),
        sa.Column("entry_prompt", sa.Text(), nullable=False),
        sa.Column(
            "is_fallback",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("role_id", "capability_id", "profile_id"),
        sa.ForeignKeyConstraint(["role_id"], ["ai_role_configs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_role_capabilities_role", "role_capabilities", ["role_id", "profile_id"])

    op.create_table(
        "habit_observations",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("habit_key", sa.String(length=128), nullable=False),
        sa.Column("habit_value", sa.String(length=255), nullable=False),
        sa.Column("habit_category", sa.String(length=32), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.String(length=128), nullable=True),
        sa.Column("source_context", sa.Text(), nullable=True),
        sa.Column(
            "has_insight_signal",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "insight_score",
            sa.Float(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_habit_observations_profile", "habit_observations", ["profile_id"]
    )
    op.create_index(
        "ix_habit_observations_key", "habit_observations", ["habit_key"]
    )

    op.create_table(
        "habit_candidates",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("habit_key", sa.String(length=128), nullable=False),
        sa.Column("habit_value", sa.String(length=255), nullable=False),
        sa.Column("habit_category", sa.String(length=32), nullable=False),
        sa.Column("evidence_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0", nullable=False),
        sa.Column("first_seen_at", sa.DateTime(), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), nullable=True),
        sa.Column("evidence_refs", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_habit_candidates_profile", "habit_candidates", ["profile_id"]
    )
    op.create_index(
        "ix_habit_candidates_status", "habit_candidates", ["status"]
    )

    op.create_table(
        "habit_audit_logs",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("candidate_id", sa.String(length=64), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("previous_status", sa.String(length=32), nullable=True),
        sa.Column("new_status", sa.String(length=32), nullable=True),
        sa.Column("actor_type", sa.String(length=32), nullable=True),
        sa.Column("actor_id", sa.String(length=64), nullable=True),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )
    op.create_index(
        "ix_habit_audit_logs_profile", "habit_audit_logs", ["profile_id"]
    )
    op.create_index(
        "ix_habit_audit_logs_candidate", "habit_audit_logs", ["candidate_id"]
    )


def downgrade():
    op.drop_index("ix_habit_audit_logs_candidate", table_name="habit_audit_logs")
    op.drop_index("ix_habit_audit_logs_profile", table_name="habit_audit_logs")
    op.drop_table("habit_audit_logs")

    op.drop_index("ix_habit_candidates_status", table_name="habit_candidates")
    op.drop_index("ix_habit_candidates_profile", table_name="habit_candidates")
    op.drop_table("habit_candidates")

    op.drop_index("ix_habit_observations_key", table_name="habit_observations")
    op.drop_index("ix_habit_observations_profile", table_name="habit_observations")
    op.drop_table("habit_observations")

    op.drop_index("ix_role_capabilities_role", table_name="role_capabilities")
    op.drop_table("role_capabilities")

    op.drop_index("ix_ai_role_usage_profile", table_name="ai_role_usage_records")
    op.drop_table("ai_role_usage_records")

    op.drop_index("ix_ai_role_configs_enabled", table_name="ai_role_configs")
    op.drop_index("ix_ai_role_configs_profile", table_name="ai_role_configs")
    op.drop_table("ai_role_configs")
