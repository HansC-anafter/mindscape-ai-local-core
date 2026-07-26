"""Add normalized device host binding and workspace grant authority.

Revision ID: 20260727120000
Revises: 20260726100000
Create Date: 2026-07-27 12:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260727120000"
down_revision = "20260726100000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")

    op.create_table(
        "host_runtime_bindings",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("capability_code", sa.String(length=128), nullable=False),
        sa.Column("requirement_code", sa.String(length=64), nullable=False),
        sa.Column("capability_version", sa.String(length=64), nullable=False),
        sa.Column("runtime_digest", sa.String(length=64), nullable=False),
        sa.Column("host_assets_digest", sa.String(length=64), nullable=False),
        sa.Column("entrypoint", sa.String(length=512), nullable=False),
        sa.Column("entrypoint_digest", sa.String(length=64), nullable=False),
        sa.Column("desired_state", sa.String(length=16), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("share_policy", sa.String(length=32), nullable=False),
        sa.Column("operations", postgresql.JSONB(), nullable=False),
        sa.Column("permission_classes", postgresql.JSONB(), nullable=False),
        sa.Column("resource_lane", sa.String(length=128), nullable=False),
        sa.Column("materialized_root", sa.Text(), nullable=True),
        sa.Column("installed_tree_digest", sa.String(length=64), nullable=True),
        sa.Column("finalizers", postgresql.JSONB(), nullable=False),
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
        sa.UniqueConstraint(
            "device_id",
            "capability_code",
            "requirement_code",
            name="uq_host_runtime_binding_identity",
        ),
        sa.CheckConstraint(
            "desired_state IN "
            "('declared','materialized','active','degraded','retiring','retired')",
            name="chk_host_runtime_binding_state",
        ),
        sa.CheckConstraint(
            "generation >= 1",
            name="chk_host_runtime_binding_generation",
        ),
        sa.CheckConstraint(
            "share_policy IN ('exclusive_workspace','workspace_grants')",
            name="chk_host_runtime_binding_share_policy",
        ),
        sa.CheckConstraint(
            "entrypoint LIKE 'scripts/%' AND entrypoint NOT LIKE '%..%'",
            name="chk_host_runtime_binding_entrypoint",
        ),
        sa.CheckConstraint(
            "runtime_digest = host_assets_digest",
            name="chk_host_runtime_binding_digest_identity",
        ),
    )
    op.create_index(
        "idx_host_runtime_bindings_projection",
        "host_runtime_bindings",
        ["capability_code", "desired_state", "device_id"],
    )

    op.create_table(
        "host_runtime_attestations",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("binding_id", sa.String(length=64), nullable=False),
        sa.Column("revision", sa.BigInteger(), nullable=False),
        sa.Column("observed_generation", sa.BigInteger(), nullable=False),
        sa.Column("runtime_digest", sa.String(length=64), nullable=False),
        sa.Column("executor_identity_digest", sa.String(length=64), nullable=False),
        sa.Column("permission_revision", sa.BigInteger(), nullable=False),
        sa.Column("conditions", postgresql.JSONB(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["host_runtime_bindings.id"],
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "binding_id",
            "revision",
            name="uq_host_runtime_attestation_revision",
        ),
        sa.CheckConstraint(
            "revision >= 1 AND observed_generation >= 1 "
            "AND permission_revision >= 1",
            name="chk_host_runtime_attestation_revisions",
        ),
        sa.CheckConstraint(
            "executor_identity_digest ~ '^[0-9a-f]{64}$'",
            name="chk_host_runtime_attestation_executor_digest",
        ),
    )
    op.create_index(
        "idx_host_runtime_attestations_latest",
        "host_runtime_attestations",
        ["binding_id", sa.text("revision DESC")],
    )

    op.create_table(
        "workspace_host_grants",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("workspace_id", sa.String(length=128), nullable=False),
        sa.Column("binding_id", sa.String(length=64), nullable=False),
        sa.Column("binding_generation", sa.BigInteger(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("operation_args_sha256", sa.String(length=64), nullable=False),
        sa.Column("policy_revision", sa.BigInteger(), nullable=False),
        sa.Column("attestation_revision", sa.BigInteger(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_code", sa.String(length=128), nullable=True),
        sa.Column("voice_profile_id", sa.String(length=128), nullable=True),
        sa.Column("reference_rights_revision", sa.BigInteger(), nullable=True),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["host_runtime_bindings.id"],
            ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "binding_id",
            "operation",
            "policy_revision",
            name="uq_workspace_host_grant_revision",
        ),
        sa.CheckConstraint(
            "status IN ('active','revoked','expired')",
            name="chk_workspace_host_grant_status",
        ),
        sa.CheckConstraint(
            "binding_generation >= 1 AND policy_revision >= 1 "
            "AND attestation_revision >= 1",
            name="chk_workspace_host_grant_revisions",
        ),
        sa.CheckConstraint(
            "operation ~ '^[a-z][a-z0-9_.-]{1,63}$' "
            "AND operation_args_sha256 ~ '^[0-9a-f]{64}$'",
            name="chk_workspace_host_grant_operation",
        ),
        sa.CheckConstraint(
            "(provider_code IS NULL AND voice_profile_id IS NULL "
            "AND reference_rights_revision IS NULL) OR "
            "(provider_code IS NOT NULL AND voice_profile_id IS NOT NULL "
            "AND reference_rights_revision >= 1)",
            name="chk_workspace_host_grant_voice_scope",
        ),
    )
    op.create_index(
        "idx_workspace_host_grants_effective",
        "workspace_host_grants",
        ["workspace_id", "binding_id", "operation", "status", "expires_at"],
    )

    op.create_table(
        "host_runtime_receipts",
        sa.Column("id", sa.String(length=64), primary_key=True),
        sa.Column("binding_id", sa.String(length=64), nullable=False),
        sa.Column("generation", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.ForeignKeyConstraint(
            ["binding_id"],
            ["host_runtime_bindings.id"],
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "generation >= 1",
            name="chk_host_runtime_receipt_generation",
        ),
        sa.CheckConstraint(
            "kind IN "
            "('declared','materialized','attested','granted','revoked',"
            "'retiring','retired')",
            name="chk_host_runtime_receipt_kind",
        ),
    )
    op.create_index(
        "idx_host_runtime_receipts_binding",
        "host_runtime_receipts",
        ["binding_id", "created_at"],
    )

    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")


def downgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")
    op.drop_index(
        "idx_host_runtime_receipts_binding",
        table_name="host_runtime_receipts",
    )
    op.drop_table("host_runtime_receipts")
    op.drop_index(
        "idx_workspace_host_grants_effective",
        table_name="workspace_host_grants",
    )
    op.drop_table("workspace_host_grants")
    op.drop_index(
        "idx_host_runtime_attestations_latest",
        table_name="host_runtime_attestations",
    )
    op.drop_table("host_runtime_attestations")
    op.drop_index(
        "idx_host_runtime_bindings_projection",
        table_name="host_runtime_bindings",
    )
    op.drop_table("host_runtime_bindings")
    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")
