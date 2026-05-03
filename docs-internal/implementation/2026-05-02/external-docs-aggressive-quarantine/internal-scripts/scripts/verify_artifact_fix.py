#!/usr/bin/env python3
"""
Verification script for artifact file_path fix

This script:
1. Lists all executions for a workspace
2. Shows artifacts for each execution
3. Verifies file_path is correctly set
"""

import sys
import os
from pathlib import Path
from datetime import datetime

# Add backend to path
backend_dir = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_dir))

from app.services.mindscape_store import MindscapeStore
from app.services.stores.tasks_store import TasksStore
import logging

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def verify_workspace_artifacts(workspace_id: str):
    """
    Verify artifacts for all executions in a workspace

    Args:
        workspace_id: Workspace ID to verify
    """
    store = MindscapeStore()
    tasks_store = TasksStore()

    # List all executions for the workspace
    executions = tasks_store.list_executions_by_workspace(workspace_id, limit=None)

    logger.info(f"Found {len(executions)} execution(s) for workspace {workspace_id}\n")

    if len(executions) == 0:
        logger.info("No executions found. Ready to test with a new execution.")
        return

    for i, execution in enumerate(executions, 1):
        logger.info(f"Execution {i}: {execution.id}")
        logger.info(f"  Status: {execution.status}")
        logger.info(f"  Created: {execution.created_at}")
        logger.info(f"  Playbook: {execution.execution_context.get('playbook_code') if execution.execution_context else 'N/A'}")

        # Get artifacts for this execution
        artifacts = store.artifacts.list_artifacts_by_workspace(workspace_id)
        execution_artifacts = [a for a in artifacts if a.execution_id == execution.id]

        logger.info(f"  Artifacts: {len(execution_artifacts)}")

        for j, artifact in enumerate(execution_artifacts, 1):
            file_path = None
            if artifact.metadata:
                file_path = artifact.metadata.get("actual_file_path") or artifact.metadata.get("file_path")
            if not file_path and artifact.storage_ref:
                file_path = artifact.storage_ref

            logger.info(f"    Artifact {j}: {artifact.title}")
            logger.info(f"      ID: {artifact.id}")
            logger.info(f"      Type: {artifact.artifact_type}")
            if file_path:
                logger.info(f"      ✅ file_path: {file_path}")
            else:
                logger.info(f"      ❌ file_path: None (missing!)")

        logger.info("")


def cleanup_old_executions(workspace_id: str, dry_run: bool = True):
    """
    Delete all execution tasks for a workspace

    Args:
        workspace_id: Workspace ID to clean up
        dry_run: If True, only show what would be deleted
    """
    tasks_store = TasksStore()

    executions = tasks_store.list_executions_by_workspace(workspace_id, limit=None)

    if dry_run:
        logger.info(f"DRY RUN: Would delete {len(executions)} execution(s)")
        for execution in executions:
            logger.info(f"  Would delete: {execution.id} (created: {execution.created_at})")
        return

    # Actually delete
    deleted_count = 0
    for execution in executions:
        try:
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

    parser = argparse.ArgumentParser(description="Verify artifact fix or cleanup old executions")
    parser.add_argument("workspace_id", help="Workspace ID")
    parser.add_argument("--cleanup", action="store_true", help="Delete old executions")
    parser.add_argument("--no-dry-run", action="store_true", help="Actually delete (use with --cleanup)")

    args = parser.parse_args()

    if args.cleanup:
        cleanup_old_executions(args.workspace_id, dry_run=not args.no_dry_run)
    else:
        verify_workspace_artifacts(args.workspace_id)

