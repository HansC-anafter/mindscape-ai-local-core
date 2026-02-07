"""Merge critical tables with artifacts branch

Revision ID: 20260127000007
Revises: 20260127000006, 20260130000009
Create Date: 2026-01-27

This is a merge migration to unify the two branches:
- 20260127000006: Critical tables (timeline_items, background_routines, etc.)
- 20260130000009: Artifacts table

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "20260127000007"
down_revision: tuple = ("20260127000006", "20260130000009")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Merge migration - no schema changes needed."""
    pass


def downgrade() -> None:
    """Merge migration - no schema changes needed."""
    pass
