"""Add MCP Events and Hook Runs tables

Revision ID: 20260211000000
Revises: 20260125000000
Create Date: 2026-02-11 00:00:00.000000

Phase 2a: Event Hook foundation tables for idempotent hook execution.
- mcp_events: audit log for all MCP-originated events
- mcp_hook_runs: idempotency dedup for hook executions
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "20260211000000"
down_revision: Union[str, None] = "20260125000000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- MCP Events (audit log) ---
    op.create_table(
        "mcp_events",
        sa.Column("event_id", sa.String(36), nullable=False),
        sa.Column("event_type", sa.String(48), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("trace_id", sa.String(64), nullable=True),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("event_id"),
    )
    op.create_index(
        "idx_mcp_events_ws",
        "mcp_events",
        ["workspace_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "idx_mcp_events_trace",
        "mcp_events",
        ["trace_id"],
        unique=False,
    )

    # --- MCP Hook Runs (idempotency dedup) ---
    op.create_table(
        "mcp_hook_runs",
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("hook_type", sa.String(32), nullable=False),
        sa.Column("workspace_id", sa.String(36), nullable=False),
        sa.Column("status", sa.String(16), server_default="completed", nullable=True),
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.PrimaryKeyConstraint("idempotency_key"),
    )
    op.create_index(
        "idx_hook_runs_ws",
        "mcp_hook_runs",
        ["workspace_id", "hook_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("mcp_hook_runs")
    op.drop_table("mcp_events")
