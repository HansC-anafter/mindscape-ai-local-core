"""Create durable capability pack install commit receipts.

Revision ID: 20260716020000
Revises: 20260715010000
Create Date: 2026-07-16 02:00:00.000000
"""

import sqlalchemy as sa
from alembic import op


revision = "20260716020000"
down_revision = "20260715010000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pack_install_commit_receipts",
        sa.Column("install_id", sa.Text(), primary_key=True),
        sa.Column("pack_id", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("manifest_hash", sa.String(length=64), nullable=False),
        sa.Column("artifact_sha256", sa.String(length=64), nullable=True),
        sa.Column("migration_receipt", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("commit_metadata", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column(
            "projection_state",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("projection_error", sa.Text(), nullable=True),
        sa.Column(
            "filesystem_cleanup_state",
            sa.Text(),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("filesystem_cleanup_error", sa.Text(), nullable=True),
        sa.Column(
            "reconcile_attempts",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("reconcile_not_before", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )
    op.create_index(
        "idx_pack_install_commit_receipts_pack_committed",
        "pack_install_commit_receipts",
        ["pack_id", sa.text("committed_at DESC")],
    )
    op.create_index(
        "idx_pack_install_commit_receipts_reconcile_due",
        "pack_install_commit_receipts",
        ["projection_state", "filesystem_cleanup_state", "reconcile_not_before"],
    )


def downgrade() -> None:
    op.drop_index(
        "idx_pack_install_commit_receipts_reconcile_due",
        table_name="pack_install_commit_receipts",
    )
    op.drop_index(
        "idx_pack_install_commit_receipts_pack_committed",
        table_name="pack_install_commit_receipts",
    )
    op.drop_table("pack_install_commit_receipts")
