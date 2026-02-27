"""Merge heads: absorb shared 20260211000000 into postgres chain

Revision ID: 20260223000002
Revises: 20260211000000, 20260223000001
Create Date: 2026-02-23

Absorbs the shared migration 20260211000000 (mcp_events, mcp_hook_runs)
into the postgres migration chain so that alembic_version has a single head.

After this migration:
  - `alembic upgrade head` works (single head)
  - The DB alembic_version table has exactly one row: 20260223000002
"""

from typing import Sequence, Union

# revision identifiers, used by Alembic.
revision: str = "20260223000002"
down_revision: Union[str, Sequence[str]] = ("20260211000000", "20260223000001")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Merge-only migration: no schema changes needed.
    # Both parent revisions are already applied.
    pass


def downgrade() -> None:
    # Merge-only: nothing to undo.
    pass
