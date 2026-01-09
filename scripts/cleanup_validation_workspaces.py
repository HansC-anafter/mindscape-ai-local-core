#!/usr/bin/env python3
"""
Cleanup Validation Workspaces Script

Removes all validation workspaces created by validate_playbooks.py
These workspaces have titles starting with "Validate:" and are used for automated testing.

Usage:
    # List validation workspaces (dry-run)
    docker compose exec backend python /app/scripts/cleanup_validation_workspaces.py --dry-run

    # Delete validation workspaces
    docker compose exec backend python /app/scripts/cleanup_validation_workspaces.py

    # Delete with specific owner
    docker compose exec backend python /app/scripts/cleanup_validation_workspaces.py --owner-user-id default-user
"""

import argparse
import sys
import os
from pathlib import Path

# Add backend to path
sys.path.insert(0, '/app/backend' if os.path.exists('/app/backend') else str(Path(__file__).parent.parent / 'backend'))

from app.services.mindscape_store import MindscapeStore
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Cleanup validation workspaces")
    parser.add_argument("--dry-run", action="store_true", help="List workspaces without deleting")
    parser.add_argument("--owner-user-id", default="default-user", help="Owner user ID to filter by")
    parser.add_argument("--title-prefix", default="Validate:", help="Title prefix to match (default: 'Validate:')")
    args = parser.parse_args()

    store = MindscapeStore()

    # List all workspaces for the owner
    workspaces = store.list_workspaces(
        owner_user_id=args.owner_user_id,
        limit=200  # Get more workspaces to find all validation ones
    )

    # Filter validation workspaces
    validation_workspaces = [
        ws for ws in workspaces
        if ws.title.startswith(args.title_prefix)
    ]

    if not validation_workspaces:
        logger.info(f"No validation workspaces found with title prefix '{args.title_prefix}'")
        return 0

    logger.info(f"Found {len(validation_workspaces)} validation workspace(s):")
    for ws in validation_workspaces:
        logger.info(f"  - {ws.id}: {ws.title} (created: {ws.created_at})")

    if args.dry_run:
        logger.info("Dry-run mode: No workspaces deleted. Run without --dry-run to delete.")
        return 0

    # Delete validation workspaces
    deleted_count = 0
    for ws in validation_workspaces:
        try:
            success = store.delete_workspace(ws.id)
            if success:
                logger.info(f"Deleted workspace: {ws.id} ({ws.title})")
                deleted_count += 1
            else:
                logger.warning(f"Failed to delete workspace: {ws.id} ({ws.title})")
        except Exception as e:
            logger.error(f"Error deleting workspace {ws.id}: {e}")

    logger.info(f"Successfully deleted {deleted_count} out of {len(validation_workspaces)} validation workspace(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())

