#!/usr/bin/env python3
"""
Cleanup script to delete old playbook executions for a workspace

This script deletes all execution tasks (tasks with execution_context)
for a specific workspace from the database.
"""

import sys
import os
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.services.mindscape_store import MindscapeStore
from app.services.stores.tasks_store import TasksStore
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def cleanup_workspace_executions(workspace_id: str, dry_run: bool = False):
    """
    Delete all execution tasks for a workspace

    Args:
        workspace_id: Workspace ID to clean up
        dry_run: If True, only show what would be deleted without actually deleting
    """
    store = MindscapeStore()
    tasks_store = TasksStore()

    # List all executions for the workspace
    executions = tasks_store.list_executions_by_workspace(workspace_id, limit=None)

    logger.info(f"Found {len(executions)} execution(s) for workspace {workspace_id}")

    if dry_run:
        logger.info("DRY RUN MODE - No deletions will be performed")
        for execution in executions:
            logger.info(f"  Would delete: {execution.id} (status: {execution.status}, created: {execution.created_at})")
        return

    # Delete each execution
    deleted_count = 0
    for execution in executions:
        try:
            # Delete from database
            with tasks_store.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM tasks WHERE id = ?', (execution.id,))
                conn.commit()
                deleted_count += 1
                logger.info(f"Deleted execution: {execution.id}")
        except Exception as e:
            logger.error(f"Failed to delete execution {execution.id}: {e}")

    logger.info(f"Successfully deleted {deleted_count} execution(s)")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cleanup old playbook executions for a workspace")
    parser.add_argument("workspace_id", help="Workspace ID to clean up")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be deleted without actually deleting")

    args = parser.parse_args()

    cleanup_workspace_executions(args.workspace_id, dry_run=args.dry_run)

