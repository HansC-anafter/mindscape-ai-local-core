"""System settings + user configs + model catalog

Revision ID: 20260129000001
Revises: 20260128000000
Create Date: 2026-01-29 00:00:00.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260129000001"
down_revision = "20260128000000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("value_type", sa.String(length=32), nullable=False),
        sa.Column(
            "category", sa.String(length=64), server_default="general", nullable=False
        ),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "is_sensitive",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_user_editable",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("key"),
    )
    op.create_index("ix_system_settings_category", "system_settings", ["category"])

    op.create_table(
        "user_configs",
        sa.Column("profile_id", sa.String(length=36), nullable=False),
        sa.Column(
            "agent_backend_mode",
            sa.String(length=32),
            server_default="local",
            nullable=False,
        ),
        sa.Column("remote_crs_url", sa.Text(), nullable=True),
        sa.Column("remote_crs_token", sa.Text(), nullable=True),
        sa.Column("openai_api_key", sa.Text(), nullable=True),
        sa.Column("anthropic_api_key", sa.Text(), nullable=True),
        sa.Column("vertex_api_key", sa.Text(), nullable=True),
        sa.Column("vertex_project_id", sa.Text(), nullable=True),
        sa.Column("vertex_location", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("profile_id"),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
    )

    op.create_table(
        "model_providers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("provider_name", sa.String(length=64), nullable=False, unique=True),
        sa.Column("api_key_setting_key", sa.String(length=255), nullable=False),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False
        ),
        sa.Column("metadata", sa.Text(), nullable=True),
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
    )

    op.create_table(
        "model_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("provider_name", sa.String(length=64), nullable=False),
        sa.Column("model_type", sa.String(length=32), nullable=False),
        sa.Column("display_name", sa.String(length=128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_latest", sa.Boolean(), server_default=sa.text("false"), nullable=False
        ),
        sa.Column(
            "is_recommended",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "is_deprecated",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("deprecation_date", sa.Text(), nullable=True),
        sa.Column("dimensions", sa.Integer(), nullable=True),
        sa.Column("context_window", sa.Integer(), nullable=True),
        sa.Column("icon", sa.Text(), nullable=True),
        sa.Column("metadata", sa.Text(), nullable=True),
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
        sa.UniqueConstraint("model_name", "provider_name", "model_type"),
    )
    op.create_index("ix_model_configs_provider", "model_configs", ["provider_name"])
    op.create_index("ix_model_configs_type", "model_configs", ["model_type"])


def downgrade():
    op.drop_index("ix_model_configs_type", table_name="model_configs")
    op.drop_index("ix_model_configs_provider", table_name="model_configs")
    op.drop_table("model_configs")
    op.drop_table("model_providers")
    op.drop_table("user_configs")
    op.drop_index("ix_system_settings_category", table_name="system_settings")
    op.drop_table("system_settings")
