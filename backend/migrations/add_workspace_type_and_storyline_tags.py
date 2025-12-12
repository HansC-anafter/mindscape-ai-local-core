"""
Migration: Add workspace_type and storyline_tags columns

This migration adds:
1. workspace_type column to workspaces table
2. storyline_tags column to intents table
3. storyline_tags column to tasks table

Revision ID: add_workspace_type_and_storyline_tags
Revises:
Create Date: 2025-12-12
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import text
import sqlite3
import os

# revision identifiers, used by Alembic.
revision = 'add_workspace_type_and_storyline_tags'
down_revision = None  # Set to previous migration ID if exists
branch_labels = None
depends_on = None


def upgrade():
    """
    Add workspace_type and storyline_tags columns.

    This migration is idempotent - it checks if columns exist before adding them.
    """
    conn = op.get_bind()

    # Add workspace_type to workspaces table
    try:
        conn.execute(text("ALTER TABLE workspaces ADD COLUMN workspace_type TEXT DEFAULT 'personal'"))
        print("Added workspace_type column to workspaces table")
    except Exception as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print("workspace_type column already exists, skipping")
        else:
            raise

    # Add storyline_tags to intents table
    try:
        conn.execute(text("ALTER TABLE intents ADD COLUMN storyline_tags TEXT"))
        print("Added storyline_tags column to intents table")
    except Exception as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print("storyline_tags column already exists in intents table, skipping")
        else:
            raise

    # Add storyline_tags to tasks table
    try:
        conn.execute(text("ALTER TABLE tasks ADD COLUMN storyline_tags TEXT"))
        print("Added storyline_tags column to tasks table")
    except Exception as e:
        if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
            print("storyline_tags column already exists in tasks table, skipping")
        else:
            raise


def downgrade():
    """
    Remove workspace_type and storyline_tags columns.

    Note: SQLite does not support DROP COLUMN directly.
    This would require recreating the table, which is complex.
    For production, consider using a more sophisticated migration strategy.
    """
    # SQLite doesn't support DROP COLUMN easily
    # In production, this would require table recreation
    # For now, we'll mark columns as deprecated rather than removing them
    print("Note: SQLite does not support DROP COLUMN. Columns will remain but be unused.")
    pass


def run_sqlite_migration(db_path: str):
    """
    Lightweight runner so local-core can apply this migration without Alembic runtime.

    Args:
        db_path: Path to SQLite database file
    """
    if not db_path:
        return

    # Ensure directory exists (matches MindscapeStore behaviour)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    with sqlite3.connect(db_path) as conn:
        cursor = conn.cursor()

        for column, ddl in [
            ("workspace_type", "TEXT DEFAULT 'personal'"),
            ("execution_mode", "TEXT DEFAULT 'qa'"),
            ("expected_artifacts", "TEXT"),
            ("execution_priority", "TEXT DEFAULT 'medium'"),
            ("project_assignment_mode", "TEXT DEFAULT 'auto_silent'"),
            ("metadata", "TEXT"),
        ]:
            try:
                cursor.execute(f"ALTER TABLE workspaces ADD COLUMN {column} {ddl}")
            except sqlite3.OperationalError:
                pass

        for table in ("intents", "tasks"):
            try:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN storyline_tags TEXT")
            except sqlite3.OperationalError:
                pass

        conn.commit()
