"""Add Tool Registry + Connections + Installed Packs

Revision ID: 20260130000002
Revises: 20260130000001
Create Date: 2026-01-30 00:00:02.000000

"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "20260130000002"
down_revision = "20260130000001"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "installed_packs",
        sa.Column("pack_id", sa.String(length=128), nullable=False),
        sa.Column(
            "installed_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column("metadata", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("pack_id"),
    )
    op.create_index("ix_installed_packs_enabled", "installed_packs", ["enabled"])

    op.create_table(
        "tool_registry",
        sa.Column("tool_id", sa.String(length=255), nullable=False),
        sa.Column("site_id", sa.String(length=255), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=True),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("origin_capability_id", sa.String(length=128), nullable=True),
        sa.Column("category", sa.String(length=128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("endpoint", sa.Text(), nullable=True),
        sa.Column("methods", sa.Text(), nullable=True),
        sa.Column("danger_level", sa.String(length=32), nullable=True),
        sa.Column("input_schema", sa.Text(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "read_only",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("allowed_agent_roles", sa.Text(), nullable=True),
        sa.Column("side_effect_level", sa.String(length=32), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("owner_profile_id", sa.String(length=64), nullable=True),
        sa.Column("capability_code", sa.String(length=128), nullable=True),
        sa.Column("risk_class", sa.String(length=32), nullable=True),
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
        sa.PrimaryKeyConstraint("tool_id"),
    )
    op.create_index("ix_tool_registry_scope", "tool_registry", ["scope"])
    op.create_index("ix_tool_registry_site", "tool_registry", ["site_id"])
    op.create_index("ix_tool_registry_tenant", "tool_registry", ["tenant_id"])
    op.create_index(
        "ix_tool_registry_owner_profile", "tool_registry", ["owner_profile_id"]
    )

    op.create_table(
        "tool_connections",
        sa.Column("id", sa.String(length=255), nullable=False),
        sa.Column("profile_id", sa.String(length=64), nullable=False),
        sa.Column("tool_type", sa.String(length=64), nullable=True),
        sa.Column("connection_type", sa.String(length=16), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("icon", sa.String(length=64), nullable=True),
        sa.Column("api_key", sa.Text(), nullable=True),
        sa.Column("api_secret", sa.Text(), nullable=True),
        sa.Column("oauth_token", sa.Text(), nullable=True),
        sa.Column("oauth_refresh_token", sa.Text(), nullable=True),
        sa.Column("base_url", sa.Text(), nullable=True),
        sa.Column("wp_url", sa.Text(), nullable=True),
        sa.Column("wp_username", sa.Text(), nullable=True),
        sa.Column("wp_application_password", sa.Text(), nullable=True),
        sa.Column("remote_cluster_url", sa.Text(), nullable=True),
        sa.Column("remote_connection_id", sa.String(length=255), nullable=True),
        sa.Column("config", sa.Text(), nullable=True),
        sa.Column("associated_roles", sa.Text(), nullable=True),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
        sa.Column(
            "is_validated",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column("last_validated_at", sa.DateTime(), nullable=True),
        sa.Column("validation_error", sa.Text(), nullable=True),
        sa.Column("usage_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
        sa.Column("last_discovery", sa.DateTime(), nullable=True),
        sa.Column("discovery_method", sa.String(length=64), nullable=True),
        sa.Column("x_platform", sa.Text(), nullable=True),
        sa.Column("data_source_type", sa.String(length=64), nullable=True),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("owner_profile_id", sa.String(length=64), nullable=True),
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
        sa.PrimaryKeyConstraint("profile_id", "id"),
    )
    op.create_index("ix_tool_connections_profile", "tool_connections", ["profile_id"])
    op.create_index("ix_tool_connections_type", "tool_connections", ["tool_type"])
    op.create_index("ix_tool_connections_active", "tool_connections", ["is_active"])


def downgrade():
    op.drop_index("ix_tool_connections_active", table_name="tool_connections")
    op.drop_index("ix_tool_connections_type", table_name="tool_connections")
    op.drop_index("ix_tool_connections_profile", table_name="tool_connections")
    op.drop_table("tool_connections")

    op.drop_index("ix_tool_registry_owner_profile", table_name="tool_registry")
    op.drop_index("ix_tool_registry_tenant", table_name="tool_registry")
    op.drop_index("ix_tool_registry_site", table_name="tool_registry")
    op.drop_index("ix_tool_registry_scope", table_name="tool_registry")
    op.drop_table("tool_registry")

    op.drop_index("ix_installed_packs_enabled", table_name="installed_packs")
    op.drop_table("installed_packs")
