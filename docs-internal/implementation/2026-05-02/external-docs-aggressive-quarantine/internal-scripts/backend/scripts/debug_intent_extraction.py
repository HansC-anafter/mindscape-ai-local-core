#!/usr/bin/env python3
"""
诊断 intent_extraction 自动执行和手动执行问题

使用方法：
1. 进入 docker 容器：
   docker exec -it mindscape-ai-local-core-backend bash

2. 运行脚本：
   python /app/backend/scripts/debug_intent_extraction.py <workspace_id>
"""

import sys
import os
import json
from pathlib import Path

# Add backend to path
backend_path = str(Path(__file__).parent.parent.parent)
sys.path.insert(0, backend_path)

try:
    from backend.app.services.stores.workspaces_store import WorkspacesStore
    from backend.app.services.stores.tasks_store import TasksStore
    from backend.app.models.workspace import TaskStatus
except ImportError:
    # Fallback for local development
    from app.services.stores.workspaces_store import WorkspacesStore
    from app.services.stores.tasks_store import TasksStore
    from app.models.workspace import TaskStatus

def main():
    if len(sys.argv) < 2:
        print("Usage: python debug_intent_extraction.py <workspace_id>")
        sys.exit(1)

    workspace_id = sys.argv[1]
    db_path = os.getenv('DATABASE_URL', 'sqlite:///./data/mindscape.db')

    # 移除 sqlite:/// 前缀
    if db_path.startswith('sqlite:///'):
        db_path = db_path.replace('sqlite:///', '')

    print(f"=== Intent Extraction 诊断工具 ===\n")
    print(f"Workspace ID: {workspace_id}")
    print(f"Database: {db_path}\n")

    # 1. 检查 workspace 配置
    print("1. 检查 Workspace 自动执行配置:")
    print("-" * 50)
    workspaces_store = WorkspacesStore(db_path)
    workspace = workspaces_store.get_workspace(workspace_id)

    if not workspace:
        print(f"❌ Workspace {workspace_id} 不存在")
        sys.exit(1)

    auto_exec_config = workspace.playbook_auto_execution_config or {}
    intent_config = auto_exec_config.get('intent_extraction', {})

    print(f"  playbook_auto_execution_config: {json.dumps(auto_exec_config, indent=2, ensure_ascii=False)}")
    print(f"\n  intent_extraction 配置:")
    print(f"    - auto_execute: {intent_config.get('auto_execute', False)}")
    print(f"    - confidence_threshold: {intent_config.get('confidence_threshold', 0.8)}")

    if not intent_config.get('auto_execute', False):
        print("\n  ⚠️  自动执行未启用！")
        print("  需要设置: playbook_auto_execution_config.intent_extraction.auto_execute = true")
    else:
        print("\n  ✅ 自动执行已启用")

    # 2. 检查 pending intent_extraction 任务
    print("\n2. 检查 Pending intent_extraction 任务:")
    print("-" * 50)
    tasks_store = TasksStore(db_path)

    # 获取所有 intent_extraction 相关任务
    all_tasks = tasks_store.list_tasks_by_workspace(workspace_id=workspace_id, limit=100)
    intent_tasks = [
        t for t in all_tasks
        if (t.pack_id == 'intent_extraction' or
            t.task_type == 'intent_extraction' or t.task_type == 'auto_intent_extraction' or
            t.task_type == 'suggestion' and t.pack_id == 'intent_extraction')
    ]

    pending_tasks = [t for t in intent_tasks if t.status == TaskStatus.PENDING]
    succeeded_tasks = [t for t in intent_tasks if t.status == TaskStatus.SUCCEEDED]
    failed_tasks = [t for t in intent_tasks if t.status == TaskStatus.FAILED]

    print(f"  总任务数: {len(intent_tasks)}")
    print(f"  - PENDING: {len(pending_tasks)}")
    print(f"  - SUCCEEDED: {len(succeeded_tasks)}")
    print(f"  - FAILED: {len(failed_tasks)}")

    if pending_tasks:
        print(f"\n  Pending 任务详情:")
        for task in pending_tasks[:5]:  # 只显示前5个
            print(f"    - Task ID: {task.id}")
            print(f"      pack_id: {task.pack_id}")
            print(f"      task_type: {task.task_type}")
            print(f"      created_at: {task.created_at}")
            print(f"      params: {json.dumps(task.params, indent=6, ensure_ascii=False) if task.params else None}")
            if task.error:
                print(f"      error: {task.error}")
            print()

    if failed_tasks:
        print(f"\n  Failed 任务详情:")
        for task in failed_tasks[:5]:  # 只显示前5个
            print(f"    - Task ID: {task.id}")
            print(f"      pack_id: {task.pack_id}")
            print(f"      task_type: {task.task_type}")
            print(f"      created_at: {task.created_at}")
            print(f"      error: {task.error}")
            print()

    # 3. 检查最近的 auto_intent_extraction 任务
    print("\n3. 检查自动执行的任务:")
    print("-" * 50)
    auto_tasks = [t for t in intent_tasks if t.task_type == 'auto_intent_extraction']
    print(f"  auto_intent_extraction 任务数: {len(auto_tasks)}")

    if auto_tasks:
        print(f"\n  最近的自动执行任务:")
        for task in auto_tasks[:3]:  # 只显示前3个
            print(f"    - Task ID: {task.id}")
            print(f"      status: {task.status}")
            print(f"      created_at: {task.created_at}")
            print(f"      params.auto_executed: {task.params.get('auto_executed') if task.params else None}")
            print()

    # 4. 检查手动执行失败的原因
    print("\n4. 检查手动执行失败原因:")
    print("-" * 50)
    if failed_tasks:
        latest_failed = failed_tasks[0]
        print(f"  最新失败任务: {latest_failed.id}")
        print(f"  Error: {latest_failed.error}")
        print(f"  Params: {json.dumps(latest_failed.params, indent=2, ensure_ascii=False) if latest_failed.params else None}")
    else:
        print("  ✅ 没有失败的任务")

    # 5. 建议
    print("\n5. 诊断建议:")
    print("-" * 50)
    if not intent_config.get('auto_execute', False):
        print("  - 启用自动执行:")
        print("    PATCH /api/v1/workspaces/{workspace_id}/playbook-auto-exec-config")
        print("    Body: {")
        print('      "playbook_code": "intent_extraction",')
        print('      "auto_execute": true,')
        print('      "confidence_threshold": 0.8')
        print("    }")

    if pending_tasks and not intent_config.get('auto_execute', False):
        print("\n  - 有 pending 任务但自动执行未启用，这些任务需要手动执行")

    if failed_tasks:
        print("\n  - 检查失败任务的 error 字段，查看具体错误原因")
        print("  - 检查后端日志: docker logs mindscape-ai-local-core-backend | grep intent_extraction")

if __name__ == '__main__':
    main()

