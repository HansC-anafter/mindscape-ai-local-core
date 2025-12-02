"""
Migration 002: Add optimized indexes for events pagination queries

This migration adds composite indexes to optimize cursor-based pagination
and workspace event queries for better performance with long conversation threads.
"""

import sqlite3
import logging

logger = logging.getLogger(__name__)


def migrate_002_add_events_pagination_index(cursor):
    """
    Add optimized indexes for events pagination

    Args:
        cursor: Database cursor
    """
    logger.info("Migration 002: Adding optimized indexes for events pagination...")

    try:
        cursor.execute("PRAGMA table_info(mind_events)")
        columns = [row[1] for row in cursor.fetchall()]

        if 'workspace_id' in columns:
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_mind_events_workspace_timestamp_id
                ON mind_events(workspace_id, timestamp DESC, id DESC)
            ''')
            logger.info("Migration 002: Added composite index for workspace events pagination")
        else:
            logger.warning("Migration 002: workspace_id column not found, skipping index creation")
    except sqlite3.OperationalError as e:
        logger.warning(f"Migration 002: Index may already exist: {e}")
