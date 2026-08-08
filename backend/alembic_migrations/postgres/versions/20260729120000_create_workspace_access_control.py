"""Create provider-neutral workspace access-control tables.

Revision ID: 20260729120000
Revises: 20260726100000
Create Date: 2026-07-29 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260729120000"
down_revision = "20260726100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")

    op.create_table(
        "access_principals",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("principal_kind", sa.String(length=16), nullable=False),
        sa.Column("display_email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "principal_kind IN ('human', 'local')",
            name="chk_access_principal_kind",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'disabled')",
            name="chk_access_principal_status",
        ),
    )

    op.create_table(
        "access_identity_bindings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("issuer", sa.String(length=512), nullable=False),
        sa.Column("subject", sa.String(length=255), nullable=False),
        sa.Column("verified_email", sa.String(length=320), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            ["access_principals.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "provider",
            "issuer",
            "subject",
            name="uq_access_identity_provider_issuer_subject",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="chk_access_identity_status",
        ),
    )
    op.create_index(
        "idx_access_identity_principal",
        "access_identity_bindings",
        ["principal_id", "status"],
    )

    op.create_table(
        "access_scope_policies",
        sa.Column("scope_type", sa.String(length=16), primary_key=True),
        sa.Column("scope_id", sa.String(length=128), primary_key=True),
        sa.Column(
            "revision",
            sa.BigInteger(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint(
            "scope_type IN ('local_core', 'workspace')",
            name="chk_access_scope_policy_type",
        ),
        sa.CheckConstraint(
            "(scope_type = 'local_core' AND scope_id = 'local-core') "
            "OR (scope_type = 'workspace' AND length(scope_id) > 0)",
            name="chk_access_scope_policy_id",
        ),
        sa.CheckConstraint(
            "revision >= 1",
            name="chk_access_scope_policy_revision",
        ),
    )

    op.create_table(
        "access_grants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("principal_id", sa.String(length=64), nullable=False),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("role_key", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            ["access_principals.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["scope_type", "scope_id"],
            ["access_scope_policies.scope_type", "access_scope_policies.scope_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "scope_type IN ('local_core', 'workspace')",
            name="chk_access_grant_scope_type",
        ),
        sa.CheckConstraint(
            "status IN ('active', 'revoked')",
            name="chk_access_grant_status",
        ),
        sa.CheckConstraint(
            "(scope_type = 'local_core' AND role_key = 'local_core_super_admin') "
            "OR (scope_type = 'workspace' AND role_key IN "
            "('workspace_owner', 'workspace_admin', "
            "'workspace_editor', 'workspace_viewer'))",
            name="chk_access_grant_role_scope",
        ),
    )
    op.create_index(
        "uq_access_grant_active_scope",
        "access_grants",
        ["principal_id", "scope_type", "scope_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
    )
    op.create_index(
        "idx_access_grant_effective_scope",
        "access_grants",
        ["principal_id", "scope_type", "scope_id", "status", "expires_at"],
    )
    op.create_index(
        "idx_access_grant_scope_role",
        "access_grants",
        ["scope_type", "scope_id", "role_key", "status"],
    )

    op.create_table(
        "access_invitations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role_key", sa.String(length=64), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("accepted_principal_id", sa.String(length=64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["scope_type", "scope_id"],
            ["access_scope_policies.scope_type", "access_scope_policies.scope_id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["accepted_principal_id"],
            ["access_principals.id"],
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "token_hash",
            name="uq_access_invitation_token_hash",
        ),
        sa.CheckConstraint(
            "scope_type IN ('local_core', 'workspace')",
            name="chk_access_invitation_scope_type",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'accepted', 'expired', 'revoked')",
            name="chk_access_invitation_status",
        ),
        sa.CheckConstraint(
            "(scope_type = 'local_core' AND role_key = 'local_core_super_admin') "
            "OR (scope_type = 'workspace' AND role_key IN "
            "('workspace_owner', 'workspace_admin', "
            "'workspace_editor', 'workspace_viewer'))",
            name="chk_access_invitation_role_scope",
        ),
    )
    op.create_index(
        "idx_access_invitation_scope_status",
        "access_invitations",
        ["scope_type", "scope_id", "status", "created_at"],
    )
    op.create_index(
        "idx_access_invitation_email_status",
        "access_invitations",
        ["email", "status", "expires_at"],
    )

    op.create_table(
        "access_audit_events",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("scope_type", sa.String(length=16), nullable=False),
        sa.Column("scope_id", sa.String(length=128), nullable=False),
        sa.Column("actor_principal_id", sa.String(length=128), nullable=False),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_principal_id", sa.String(length=64), nullable=True),
        sa.Column(
            "metadata_json",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["scope_type", "scope_id"],
            ["access_scope_policies.scope_type", "access_scope_policies.scope_id"],
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "scope_type IN ('local_core', 'workspace')",
            name="chk_access_audit_scope_type",
        ),
    )
    op.create_index(
        "idx_access_audit_scope_created",
        "access_audit_events",
        ["scope_type", "scope_id", "created_at"],
    )

    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")


def downgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")
    op.drop_index("idx_access_audit_scope_created", table_name="access_audit_events")
    op.drop_table("access_audit_events")
    op.drop_index(
        "idx_access_invitation_email_status",
        table_name="access_invitations",
    )
    op.drop_index(
        "idx_access_invitation_scope_status",
        table_name="access_invitations",
    )
    op.drop_table("access_invitations")
    op.drop_index("idx_access_grant_scope_role", table_name="access_grants")
    op.drop_index("idx_access_grant_effective_scope", table_name="access_grants")
    op.drop_index("uq_access_grant_active_scope", table_name="access_grants")
    op.drop_table("access_grants")
    op.drop_table("access_scope_policies")
    op.drop_index(
        "idx_access_identity_principal",
        table_name="access_identity_bindings",
    )
    op.drop_table("access_identity_bindings")
    op.drop_table("access_principals")
    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")
