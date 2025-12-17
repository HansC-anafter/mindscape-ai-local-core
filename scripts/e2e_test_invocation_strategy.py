#!/usr/bin/env python3
"""
E2E 測試腳本 - Playbook Invocation Strategy
在 Docker 容器內執行完整的端到端測試
"""
import asyncio
import sys
import os
import json
from datetime import datetime

sys.path.insert(0, '/app/backend')

from backend.app.services.playbook_service import PlaybookService
from backend.app.models.playbook import (
    PlaybookInvocationContext,
    InvocationMode,
    InvocationStrategy,
    InvocationTolerance,
    PlanContext
)


async def test_standalone_mode_e2e():
    """E2E 測試 Standalone Mode"""
    print("=" * 60)
    print("E2E 測試 1: Standalone Mode (Direct Path)")
    print("=" * 60)

    service = PlaybookService()

    # 獲取 playbook
    playbooks = await service.list_playbooks(locale="zh-TW")
    if not playbooks:
        print("❌ 沒有找到 playbooks")
        return False

    playbook_code = playbooks[0].playbook_code
    print(f"使用 playbook: {playbook_code}")

    # 創建 standalone context
    context = PlaybookInvocationContext(
        mode=InvocationMode.STANDALONE,
        strategy=InvocationStrategy(
            max_lookup_rounds=3,
            tolerance=InvocationTolerance.ADAPTIVE
        ),
        trace_id=f"e2e-standalone-{datetime.now().timestamp()}"
    )

    print(f"\nContext 配置:")
    print(f"  Mode: {context.mode}")
    print(f"  Max lookup rounds: {context.strategy.max_lookup_rounds}")
    print(f"  Tolerance: {context.strategy.tolerance}")

    try:
        print(f"\n執行 playbook (standalone mode)...")
        result = await service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id="e2e-test-workspace",
            profile_id="e2e-test-user",
            inputs={"query": "E2E test query"},
            context=context
        )

        print(f"✅ 執行成功")
        print(f"  Execution ID: {result.execution_id}")
        print(f"  Status: {result.status}")

        return True

    except Exception as e:
        print(f"❌ 執行失敗: {type(e).__name__}: {str(e)[:200]}")
        return False


async def test_plan_node_mode_e2e():
    """E2E 測試 Plan Node Mode"""
    print("\n" + "=" * 60)
    print("E2E 測試 2: Plan Node Mode (Plan Path)")
    print("=" * 60)

    service = PlaybookService()

    # 獲取 playbook
    playbooks = await service.list_playbooks(locale="zh-TW")
    if not playbooks:
        print("❌ 沒有找到 playbooks")
        return False

    playbook_code = playbooks[0].playbook_code
    print(f"使用 playbook: {playbook_code}")

    # 創建 plan_node context
    plan_context = PlanContext(
        plan_summary="E2E 測試計劃摘要",
        reasoning="E2E 測試推理",
        steps=[
            {"step_id": "S1", "intent": "執行測試步驟1"},
            {"step_id": "S2", "intent": "執行測試步驟2"}
        ],
        dependencies=["task-1"]
    )

    context = PlaybookInvocationContext(
        mode=InvocationMode.PLAN_NODE,
        plan_id=f"e2e-plan-{datetime.now().timestamp()}",
        task_id=f"e2e-task-{datetime.now().timestamp()}",
        plan_context=plan_context,
        visible_state={"fromPlan": {"test_data": "test_value"}},
        strategy=InvocationStrategy(
            max_lookup_rounds=1,
            tolerance=InvocationTolerance.STRICT,
            wait_for_upstream_tasks=True
        ),
        trace_id=f"e2e-plan-{datetime.now().timestamp()}"
    )

    print(f"\nContext 配置:")
    print(f"  Mode: {context.mode}")
    print(f"  Plan ID: {context.plan_id}")
    print(f"  Task ID: {context.task_id}")
    print(f"  Max lookup rounds: {context.strategy.max_lookup_rounds}")
    print(f"  Tolerance: {context.strategy.tolerance}")
    print(f"  Dependencies: {plan_context.dependencies}")

    try:
        print(f"\n執行 playbook (plan_node mode)...")
        result = await service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id="e2e-test-workspace",
            profile_id="e2e-test-user",
            inputs={"query": "E2E test query", "fromPlan": {"test_data": "test_value"}},
            context=context
        )

        print(f"✅ 執行成功")
        print(f"  Execution ID: {result.execution_id}")
        print(f"  Status: {result.status}")

        return True

    except Exception as e:
        print(f"❌ 執行失敗: {type(e).__name__}: {str(e)[:200]}")
        return False


async def test_insufficient_data_e2e():
    """E2E 測試 Plan Node Mode - 資料不足"""
    print("\n" + "=" * 60)
    print("E2E 測試 3: Plan Node Mode - 資料不足處理")
    print("=" * 60)

    service = PlaybookService()

    playbooks = await service.list_playbooks(locale="zh-TW")
    if not playbooks:
        return False

    playbook_code = playbooks[0].playbook_code

    # 創建沒有資料的 plan_node context
    context = PlaybookInvocationContext(
        mode=InvocationMode.PLAN_NODE,
        plan_id="e2e-plan-no-data",
        strategy=InvocationStrategy(
            tolerance=InvocationTolerance.STRICT
        ),
        trace_id="e2e-test-no-data"
    )

    print(f"測試資料不足情況 (STRICT tolerance)...")

    try:
        result = await service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id="e2e-test-workspace",
            profile_id="e2e-test-user",
            inputs={},  # 空 inputs，模擬資料不足
            context=context
        )

        print(f"⚠️  執行成功（但應該報錯）")
        return False

    except ValueError as e:
        if "Plan input insufficient" in str(e):
            print(f"✅ 正確報錯: {str(e)[:100]}")
            return True
        else:
            print(f"⚠️  報錯但訊息不對: {str(e)[:100]}")
            return False
    except Exception as e:
        print(f"⚠️  其他錯誤: {type(e).__name__}: {str(e)[:100]}")
        return False


async def test_backward_compatibility_e2e():
    """E2E 測試向後相容性"""
    print("\n" + "=" * 60)
    print("E2E 測試 4: 向後相容性 (無 Context)")
    print("=" * 60)

    service = PlaybookService()

    playbooks = await service.list_playbooks(locale="zh-TW")
    if not playbooks:
        return False

    playbook_code = playbooks[0].playbook_code

    print(f"測試無 context 執行 (legacy 行為)...")

    try:
        # 不傳 context
        result = await service.execute_playbook(
            playbook_code=playbook_code,
            workspace_id="e2e-test-workspace",
            profile_id="e2e-test-user",
            inputs={"query": "test"},
            # context=None (不傳)
        )

        print(f"✅ Legacy 執行成功")
        print(f"  Execution ID: {result.execution_id}")
        print(f"  Status: {result.status}")

        return True

    except Exception as e:
        print(f"❌ Legacy 執行失敗: {type(e).__name__}: {str(e)[:200]}")
        return False


async def main():
    """主測試函數"""
    print("\n" + "=" * 60)
    print("Playbook Invocation Strategy - E2E 測試")
    print("=" * 60 + "\n")

    results = {
        "standalone": False,
        "plan_node": False,
        "insufficient_data": False,
        "backward_compat": False
    }

    try:
        # 測試 1: Standalone Mode
        results["standalone"] = await test_standalone_mode_e2e()

        # 測試 2: Plan Node Mode
        results["plan_node"] = await test_plan_node_mode_e2e()

        # 測試 3: 資料不足處理
        results["insufficient_data"] = await test_insufficient_data_e2e()

        # 測試 4: 向後相容性
        results["backward_compat"] = await test_backward_compatibility_e2e()

        # 總結
        print("\n" + "=" * 60)
        print("E2E 測試結果總結")
        print("=" * 60)
        print(f"Standalone Mode:        {'✅ 通過' if results['standalone'] else '❌ 失敗'}")
        print(f"Plan Node Mode:         {'✅ 通過' if results['plan_node'] else '❌ 失敗'}")
        print(f"資料不足處理:          {'✅ 通過' if results['insufficient_data'] else '❌ 失敗'}")
        print(f"向後相容性:            {'✅ 通過' if results['backward_compat'] else '❌ 失敗'}")

        passed = sum(results.values())
        total = len(results)
        print(f"\n總計: {passed}/{total} 通過")

        if passed == total:
            print("\n🎉 所有 E2E 測試通過！")
            return 0
        else:
            print(f"\n⚠️  有 {total - passed} 個測試失敗")
            return 1

    except Exception as e:
        print(f"\n❌ E2E 測試過程中發生錯誤: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)


