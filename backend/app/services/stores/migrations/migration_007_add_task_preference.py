"""
Migration 007: Add task_preference table

Creates the task_preference table for storing user preferences on task types and packs.
This enables personalization of task recommendations based on user feedback and preferences.

Date: 2025-12-01
"""
import logging

logger = logging.getLogger(__name__)


def migrate_007_add_task_preference(cursor):
    """
    Apply migration 007: Add task_preference table

    Creates table to track user preferences for packs/task_types:
    - Which packs should be auto-suggested
    - Rejection/acceptance counts
    - Last feedback action
    """
    logger.info("Applying migration 007: Add task_preference table")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_preference (
            id TEXT PRIMARY KEY,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            pack_id TEXT,
            task_type TEXT,
            action TEXT NOT NULL,
            auto_suggest INTEGER NOT NULL DEFAULT 1,
            last_feedback TEXT,
            reject_count_30d INTEGER NOT NULL DEFAULT 0,
            accept_count_30d INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id),
            UNIQUE(workspace_id, user_id, pack_id, task_type)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_workspace ON task_preference(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_user ON task_preference(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_pack ON task_preference(pack_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_task_type ON task_preference(task_type)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_auto_suggest ON task_preference(auto_suggest)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_preference_workspace_user ON task_preference(workspace_id, user_id)')

    logger.info("Migration 007 completed: task_preference table created")


def rollback_007_add_task_preference(cursor):
    """Rollback migration 007"""
    logger.info("Rolling back migration 007: Remove task_preference table")
    cursor.execute('DROP TABLE IF EXISTS task_preference')
    logger.info("Migration 007 rolled back: task_preference table removed")

