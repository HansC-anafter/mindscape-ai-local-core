"""
Migration 003: Add artifacts table

Creates the artifacts table for storing playbook output artifacts.
"""

import logging

logger = logging.getLogger(__name__)


def migrate_003_add_artifacts_table(cursor):
    """Apply migration 003"""
    from backend.app.services.stores.schema import init_artifacts_schema

    logger.info("Applying migration 003: Add artifacts table")
    init_artifacts_schema(cursor)
    logger.info("Migration 003 completed")


def rollback_003_add_artifacts_table(cursor):
    """Rollback migration 003"""
    logger.info("Rolling back migration 003: Drop artifacts table")
    cursor.execute('DROP TABLE IF EXISTS artifacts')
    logger.info("Rollback 003 completed")

