#!/usr/bin/env python3
"""
Cleanup stuck playbook executions

This script cancels or marks as failed all running executions that are stuck.
"""

import sys
import os
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.app.services.stores.tasks_store import TasksStore
from backend.app.models.workspace import TaskStatus
from backend.app.services.mindscape_store import MindscapeStore


def cleanup_stuck_executions(
    workspace_id: str,
    older_than_hours: int = 1,
    dry_run: bool = True
):
    """
    Cleanup stuck executions

    Args:
        workspace_id: Workspace ID
        older_than_hours: Only cleanup executions older than this many hours
        dry_run: If True, only show what would be done without actually updating
    """
    store = MindscapeStore()
    tasks_store = TasksStore(db_path=store.db_path)

    # Get all running playbook executions
    all_tasks = tasks_store.list_tasks_by_workspace(workspace_id=workspace_id)
    running_tasks = [
        t for t in all_tasks
        if t.task_type == "playbook_execution" and t.status == TaskStatus.RUNNING
    ]

    print(f"=== 找到 {len(running_tasks)} 個 Running 狀態的執行 ===\n")

    if not running_tasks:
        print("✅ 沒有卡住的執行")
        return

    # Filter by age
    cutoff_time = datetime.utcnow() - timedelta(hours=older_than_hours)
    stuck_tasks = []

    for task in running_tasks:
        task_time = task.created_at if task.created_at else task.started_at
        if task_time and task_time < cutoff_time:
            stuck_tasks.append(task)

    if not stuck_tasks:
        print(f"✅ 沒有超過 {older_than_hours} 小時的卡住執行")
        return

    print(f"=== 發現 {len(stuck_tasks)} 個卡住的執行（超過 {older_than_hours} 小時）===\n")

    for task in stuck_tasks:
        age_hours = (datetime.utcnow() - task.created_at).total_seconds() / 3600 if task.created_at else 0
        print(f"執行 ID: {task.execution_id}")
        print(f"  Playbook: {task.pack_id}")
        print(f"  創建時間: {task.created_at}")
        print(f"  已卡住: {age_hours:.1f} 小時")

        if not dry_run:
            # Update task status to FAILED
            try:
                tasks_store.update_task_status(
                    task_id=task.id,
                    status=TaskStatus.FAILED,
                    error="Execution stuck and cleaned up by script",
                    completed_at=datetime.utcnow()
                )
                print(f"  ✅ 已標記為 FAILED")
            except Exception as e:
                print(f"  ❌ 更新失敗: {e}")
        else:
            print(f"  [DRY RUN] 將標記為 FAILED")
        print()

    if dry_run:
        print("\n⚠️  DRY RUN 模式：未實際更新數據庫")
        print("要實際執行清理，請使用: --execute")
    else:
        print(f"\n✅ 已清理 {len(stuck_tasks)} 個卡住的執行")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Cleanup stuck playbook executions")
    parser.add_argument(
        "--workspace-id",
        default="931820cc-9bdc-4299-bb29-a439ea8f82a2",
        help="Workspace ID"
    )
    parser.add_argument(
        "--older-than-hours",
        type=int,
        default=1,
        help="Only cleanup executions older than this many hours (default: 1)"
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually execute the cleanup (default is dry-run)"
    )

    args = parser.parse_args()

    cleanup_stuck_executions(
        workspace_id=args.workspace_id,
        older_than_hours=args.older_than_hours,
        dry_run=not args.execute
    )

