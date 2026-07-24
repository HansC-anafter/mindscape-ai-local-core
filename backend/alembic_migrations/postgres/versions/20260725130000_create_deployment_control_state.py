"""Create the generic deployment-control singleton.

Revision ID: 20260725130000
Revises: 20260725120000
Create Date: 2026-07-25 13:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260725130000"
down_revision = "20260725120000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")
    op.create_table(
        "deployment_control_state",
        sa.Column(
            "id",
            sa.SmallInteger(),
            primary_key=True,
            server_default="1",
        ),
        sa.Column("mode", sa.String(length=32), nullable=False),
        sa.Column("provider_code", sa.String(length=64), nullable=True),
        sa.Column("active_envelope", postgresql.JSONB(), nullable=True),
        sa.Column("envelope_hash", sa.String(length=64), nullable=True),
        sa.Column("issuer", sa.String(length=128), nullable=True),
        sa.Column("key_id", sa.String(length=128), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("envelope_revision", sa.BigInteger(), nullable=True),
        sa.Column(
            "state_revision",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("updated_by", sa.String(length=128), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
        sa.CheckConstraint("id = 1", name="chk_deployment_control_singleton"),
        sa.CheckConstraint(
            "mode IN ('unmanaged_local', 'provider_managed')",
            name="chk_deployment_control_mode",
        ),
        sa.CheckConstraint(
            "state_revision >= 1",
            name="chk_deployment_control_state_revision",
        ),
        sa.CheckConstraint(
            "("
            "mode = 'unmanaged_local' AND provider_code IS NULL "
            "AND active_envelope IS NULL AND envelope_hash IS NULL "
            "AND issuer IS NULL AND key_id IS NULL AND expires_at IS NULL "
            "AND envelope_revision IS NULL"
            ") OR ("
            "mode = 'provider_managed' AND provider_code IS NOT NULL "
            "AND active_envelope IS NOT NULL AND envelope_hash IS NOT NULL "
            "AND issuer IS NOT NULL AND key_id IS NOT NULL "
            "AND expires_at IS NOT NULL AND envelope_revision IS NOT NULL "
            "AND envelope_revision >= 1"
            ")",
            name="chk_deployment_control_state_shape",
        ),
    )
    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")


def downgrade() -> None:
    op.execute("SET lock_timeout = '15s'")
    op.execute("SET statement_timeout = '120s'")
    op.drop_table("deployment_control_state")
    op.execute("RESET statement_timeout")
    op.execute("RESET lock_timeout")
