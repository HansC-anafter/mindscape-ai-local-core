"""merge projects migration branch

Revision ID: d09e1f9b13d4
Revises: 004_add_playbook_flows, 77e8e5c96835
Create Date: 2025-12-07 23:54:23.747233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd09e1f9b13d4'
down_revision: Union[str, None] = ('004_add_playbook_flows', '77e8e5c96835')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

