"""
Migration 005: Add readiness_status and tool_statuses to background_routines table

Adds system-managed readiness status fields for background routines:
- readiness_status: ready / needs_setup / unsupported
- tool_statuses: JSON mapping tool_type -> status
- error_count: Consecutive error count (for auto-pause)
- auto_paused: Whether routine was auto-paused due to errors

These fields are stored as separate columns (not in config JSON) for:
- Better query performance
- Clear separation between system-managed status and playbook-specific config
"""
import logging

logger = logging.getLogger(__name__)


def migrate_005_add_readiness_status(cursor):
    """
    Apply migration 005: Add readiness status fields to background_routines

    Adds:
    - readiness_status: TEXT (ready/needs_setup/unsupported)
    - tool_statuses: TEXT (JSON string mapping tool_type -> status)
    - error_count: INTEGER DEFAULT 0
    - auto_paused: INTEGER DEFAULT 0
    """
    logger.info("Applying migration 005: Add readiness status to background_routines")

    # Add new columns
    for column_def in [
        ('readiness_status', 'TEXT'),
        ('tool_statuses', 'TEXT'),
        ('error_count', 'INTEGER DEFAULT 0'),
        ('auto_paused', 'INTEGER DEFAULT 0')
    ]:
        column_name, column_type = column_def
        try:
            cursor.execute(f'ALTER TABLE background_routines ADD COLUMN {column_name} {column_type}')
            logger.info(f"Added column {column_name} to background_routines")
        except Exception as e:
            # If column already exists, ignore error
            if "duplicate column name" not in str(e).lower() and "already exists" not in str(e).lower():
                raise
            logger.warning(f"Column {column_name} may already exist: {e}")

    logger.info("Migration 005 completed: Added readiness status fields to background_routines")


def rollback_005_add_readiness_status(cursor):
    """Rollback migration 005"""
    logger.info("Rolling back migration 005: Remove readiness status from background_routines")
    # SQLite does not support DROP COLUMN, rollback requires table recreation
    logger.warning("SQLite does not support DROP COLUMN. Rollback requires table recreation.")

