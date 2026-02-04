"""Add workspace blueprint fields

Revision ID: 006_add_workspace_blueprint_fields
Revises: 005_add_web_generation_baselines_tables
Create Date: 2025-12-13

Adds workspace_blueprint, launch_status, and starter_kit_type fields to workspaces table
for workspace launch enhancement feature.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import sqlite

# revision identifiers, used by Alembic.
revision: str = '006_add_workspace_blueprint_fields'
down_revision: str = '005_add_web_generation_baselines'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add workspace blueprint fields to workspaces table"""
    # Add workspace_blueprint JSON field (nullable=True)
    op.add_column('workspaces', sa.Column('workspace_blueprint', sa.JSON(), nullable=True))

    # Add launch_status TEXT field (NOT NULL, default='pending')
    # Important: launch_status must be NOT NULL + default, because routing depends on it
    op.add_column('workspaces', sa.Column('launch_status', sa.String(), nullable=False, server_default='pending'))

    # Add starter_kit_type TEXT field (nullable=True)
    op.add_column('workspaces', sa.Column('starter_kit_type', sa.String(), nullable=True))


def downgrade() -> None:
    """Remove workspace blueprint fields from workspaces table"""
    op.drop_column('workspaces', 'starter_kit_type')
    op.drop_column('workspaces', 'launch_status')
    op.drop_column('workspaces', 'workspace_blueprint')

