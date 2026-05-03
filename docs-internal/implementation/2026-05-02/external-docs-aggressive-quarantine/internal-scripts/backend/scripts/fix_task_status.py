#!/usr/bin/env python3
"""
Fix Task Status Script

Fixes tasks that have execution_context.status = "completed" but task.status = "running".

Usage:
    python3 fix_task_status.py [workspace_id] [--create-timeline-items] [--limit N]
"""

import sys
import os
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.services.task_status_fix import TaskStatusFixService
from app.services.mindscape_store import MindscapeStore


def main():
    parser = argparse.ArgumentParser(description='Fix task status inconsistencies')
    parser.add_argument('workspace_id', nargs='?', help='Workspace ID (optional, fixes all workspaces if not provided)')
    parser.add_argument('--create-timeline-items', action='store_true', default=True,
                        help='Create timeline items for fixed tasks (default: True)')
    parser.add_argument('--no-timeline-items', dest='create_timeline_items', action='store_false',
                        help='Do not create timeline items')
    parser.add_argument('--limit', type=int, help='Maximum number of tasks to fix')
    args = parser.parse_args()

    store = MindscapeStore()
    service = TaskStatusFixService(store)

    result = service.fix_all_inconsistent_tasks(
        workspace_id=args.workspace_id,
        create_timeline_items=args.create_timeline_items,
        limit=args.limit
    )

    print(f"\n=== Task Status Fix Summary ===")
    print(f"Total found: {result['total_found']}")
    print(f"Total fixed: {result['total_fixed']}")
    print(f"Total failed: {result['total_failed']}")

    if result['results']:
        print(f"\n=== Fixed Tasks ===")
        for r in result['results']:
            if r.get('fixed'):
                print(f"  ✓ {r['task_id']}: {r['old_status']} -> {r['new_status']} ({r.get('playbook_code', 'unknown')})")
                if r.get('timeline_item_created'):
                    print(f"    → Timeline item created: {r.get('timeline_item_id')}")
            else:
                print(f"  ✗ {r['task_id']}: {r.get('reason', r.get('error', 'unknown error'))}")

    return 0 if result['total_failed'] == 0 else 1


if __name__ == '__main__':
    sys.exit(main())

