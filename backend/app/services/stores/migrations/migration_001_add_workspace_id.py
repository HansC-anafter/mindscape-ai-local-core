"""
Migration 001: Add workspace_id column to mind_events and intent_logs tables

This migration handles existing databases that were created before workspace support was added.
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def migrate_001_add_workspace_id(cursor):
    """
    Add workspace_id column to mind_events and intent_logs tables if they don't exist

    Args:
        cursor: Database cursor
    """
    # Check if workspace_id column exists in mind_events table
    cursor.execute("PRAGMA table_info(mind_events)")
    columns = [row[1] for row in cursor.fetchall()]

    if 'workspace_id' not in columns:
        logger.info("Migration 001: Adding workspace_id column to mind_events table...")
        try:
            cursor.execute('''
                ALTER TABLE mind_events
                ADD COLUMN workspace_id TEXT
            ''')
            # Recreate index with workspace_id
            cursor.execute('DROP INDEX IF EXISTS idx_mind_events_workspace')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_workspace ON mind_events(workspace_id)')
            cursor.execute('DROP INDEX IF EXISTS idx_mind_events_workspace_timestamp')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_mind_events_workspace_timestamp ON mind_events(workspace_id, timestamp DESC)')
            logger.info("Migration 001: workspace_id column added to mind_events")
        except sqlite3.OperationalError as e:
            logger.warning(f"Migration 001: Skipped (column may already exist): {e}")

    # Check if workspace_id column exists in intent_logs table
    cursor.execute("PRAGMA table_info(intent_logs)")
    intent_logs_columns = [row[1] for row in cursor.fetchall()]

    if 'workspace_id' not in intent_logs_columns:
        logger.info("Migration 001: Adding workspace_id column to intent_logs table...")
        try:
            cursor.execute('''
                ALTER TABLE intent_logs
                ADD COLUMN workspace_id TEXT
            ''')
            # Recreate index with workspace_id
            cursor.execute('DROP INDEX IF EXISTS idx_intent_logs_workspace')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_logs_workspace ON intent_logs(workspace_id)')
            cursor.execute('DROP INDEX IF EXISTS idx_intent_logs_workspace_timestamp')
            cursor.execute('CREATE INDEX IF NOT EXISTS idx_intent_logs_workspace_timestamp ON intent_logs(workspace_id, timestamp DESC)')
            logger.info("Migration 001: workspace_id column added to intent_logs")
        except sqlite3.OperationalError as e:
            logger.warning(f"Migration 001: Skipped (column may already exist): {e}")
