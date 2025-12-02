"""
Migration 006: Add task_feedback table and extend TaskStatus enum

This migration:
1. Creates task_feedback table to track user feedback on AI-generated tasks
2. The TaskStatus enum extension (CANCELLED_BY_USER, EXPIRED) is handled in code,
   no database migration needed as status is stored as TEXT

Date: 2025-01-02
"""
import logging

logger = logging.getLogger(__name__)


def migrate_006_add_task_feedback(cursor):
    """
    Apply migration 006: Add task_feedback table

    Creates table to track user feedback (rejections, dismissals, acceptances)
    on AI-generated tasks for improving recommendation strategies.
    """
    logger.info("Applying migration 006: Add task_feedback table")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS task_feedback (
            id TEXT PRIMARY KEY,
            task_id TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            action TEXT NOT NULL,
            reason_code TEXT,
            comment TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (task_id) REFERENCES tasks (id),
            FOREIGN KEY (workspace_id) REFERENCES workspaces (id)
        )
    ''')

    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_task ON task_feedback(task_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_workspace ON task_feedback(workspace_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_user ON task_feedback(user_id)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_action ON task_feedback(action)')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_task_feedback_created_at ON task_feedback(created_at DESC)')

    logger.info("Migration 006 completed: task_feedback table created")


def rollback_006_add_task_feedback(cursor):
    """Rollback migration 006"""
    logger.info("Rolling back migration 006: Remove task_feedback table")
    cursor.execute('DROP TABLE IF EXISTS task_feedback')
    logger.info("Migration 006 rolled back: task_feedback table removed")

