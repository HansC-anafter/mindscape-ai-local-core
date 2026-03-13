"""Add meeting_enabled column to workspaces

Revision ID: 20260310200000
Revises: 20260301110000
Create Date: 2026-03-10 20:00:00.000000

Orthogonal meeting engine flag: decouples meeting engine activation
from execution_mode. Any execution_mode (qa/hybrid/execution) can
have meeting engine enabled via this flag.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.engine.reflection import Inspector

# revision identifiers, used by Alembic.
revision: str = "20260310200000"
down_revision: Union[str, None] = "20260301110000"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns("workspaces")]
    if "meeting_enabled" not in columns:
        op.add_column(
            "workspaces",
            sa.Column(
                "meeting_enabled",
                sa.Boolean(),
                server_default=sa.text("false"),
                nullable=False,
            ),
        )


def downgrade() -> None:
    conn = op.get_bind()
    inspector = Inspector.from_engine(conn)
    columns = [col['name'] for col in inspector.get_columns("workspaces")]
    if "meeting_enabled" in columns:
        op.drop_column("workspaces", "meeting_enabled")
