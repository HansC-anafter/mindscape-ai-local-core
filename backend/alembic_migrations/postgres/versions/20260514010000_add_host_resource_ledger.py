"""Add host resource durable ledger tables.

Revision ID: 20260514010000
Revises: 20260513203000
Create Date: 2026-05-14 01:00:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260514010000"
down_revision = "20260513203000"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "host_resource_reservations",
        sa.Column("reservation_id", sa.Text(), primary_key=True),
        sa.Column("state", sa.Text(), nullable=False),
        sa.Column("target_lane", sa.Text(), nullable=True),
        sa.Column("priority_class", sa.Text(), nullable=True),
        sa.Column("drain_policy", sa.Text(), nullable=True),
        sa.Column("preemption_policy", sa.Text(), nullable=True),
        sa.Column("resume_policy", sa.Text(), nullable=True),
        sa.Column("requested_by", sa.Text(), nullable=True),
        sa.Column(
            "route_request",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "metadata",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "host_resource_events",
        sa.Column("event_id", sa.Text(), primary_key=True),
        sa.Column("reservation_id", sa.Text(), nullable=True),
        sa.Column("event_type", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("source", sa.Text(), nullable=True),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("task_id", sa.Text(), nullable=True),
        sa.Column("runner_id", sa.Text(), nullable=True),
        sa.Column("lane_id", sa.Text(), nullable=True),
        sa.Column(
            "payload",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_reservations_active
        ON host_resource_reservations (state, expires_at, created_at DESC)
        WHERE state IN ('reserved_waiting', 'permitted')
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_reservations_lane_created
        ON host_resource_reservations (target_lane, created_at DESC)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_events_reservation_time
        ON host_resource_events (reservation_id, occurred_at DESC, event_id)
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_host_resource_events_type_time
        ON host_resource_events (event_type, occurred_at DESC)
        """
    )


def downgrade():
    op.drop_index("idx_host_resource_events_type_time", table_name="host_resource_events")
    op.drop_index(
        "idx_host_resource_events_reservation_time",
        table_name="host_resource_events",
    )
    op.drop_index(
        "idx_host_resource_reservations_lane_created",
        table_name="host_resource_reservations",
    )
    op.drop_index(
        "idx_host_resource_reservations_active",
        table_name="host_resource_reservations",
    )
    op.drop_table("host_resource_events")
    op.drop_table("host_resource_reservations")
