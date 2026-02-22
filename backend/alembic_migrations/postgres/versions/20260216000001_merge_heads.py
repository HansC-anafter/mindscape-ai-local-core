"""Merge heads: 20260211000000 + 20260215000001

Revision ID: 20260216000001
Revises: 20260215000001
Create Date: 2026-02-16 00:00:01.000000

Bridges the shared-versions migration 20260211000000 (mcp_events / hook_runs)
with the postgres-versions migration 20260215000001 (runtime auth_status)
into a single head.

NOTE: down_revision is single-parent to avoid cross-directory overlap error.
The shared migration 20260211000000 is referenced via depends_on so alembic
still enforces ordering without creating a multi-directory merge node.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260216000001"
down_revision: Union[str, None] = "20260215000001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
