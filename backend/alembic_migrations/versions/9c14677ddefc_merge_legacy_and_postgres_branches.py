"""Merge legacy and postgres branches

Revision ID: 9c14677ddefc
Revises: 20260125000000, 20260105000000, 20260129000000
Create Date: 2026-01-25 08:23:06.931395

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9c14677ddefc"
down_revision: Union[str, None] = ("20260125000000", "20260105000000", "20260129000000")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
