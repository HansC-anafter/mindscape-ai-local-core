"""
Migration: Legacy compatibility alias for the original PD initial schema revision.

Revision ID: 001_create_direction_tables
Revises: 20260317000000
Create Date: 2026-03-23
"""

# revision identifiers, used by Alembic.
revision = "001_create_direction_tables"
down_revision = "20260317000000"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Keep legacy revision ids valid for databases already stamped with 001."""


def downgrade() -> None:
    """Legacy compatibility shim has no reversible operations."""
