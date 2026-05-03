# Docker 實測命令

## 快速測試結果

✅ **Context 創建測試通過**
- Standalone: mode=STANDALONE, max_rounds=3, tolerance=ADAPTIVE
- Plan Node: mode=PLAN_NODE, max_rounds=1, tolerance=STRICT

✅ **找到 64 個 playbooks**
- 建議測試: `data_analysis`

## 實測步驟

### 1. 進入 Docker 容器

```bash
docker compose exec backend bash
```

### 2. 測試 Context 創建（已通過）

```bash
python -c "
from backend.app.services.conversation.execution_launcher import ExecutionLauncher
from backend.app.models.playbook import PlanContext

launcher = ExecutionLauncher()
ctx1 = launcher._create_invocation_context(plan_id=None, trace_id='test-1')
print(f'Standalone: {ctx1.mode}, rounds={ctx1.strategy.max_lookup_rounds}')

plan_ctx = PlanContext(plan_summary='Test', reasoning='Test', steps=[], dependencies=[])
ctx2 = launcher._create_invocation_context(plan_id='plan-1', plan_context=plan_ctx, trace_id='test-2')
print(f'Plan Node: {ctx2.mode}, rounds={ctx2.strategy.max_lookup_rounds}')
"
```

### 3. 測試 Standalone Mode (Direct Path)

在容器外執行：

```bash
# 測試直接執行 playbook（應該使用 standalone 模式）
curl -X POST "http://localhost:8000/api/v1/playbooks/execute/start?playbook_code=data_analysis&profile_id=test-user&workspace_id=test-workspace" \
  -H "Content-Type: application/json" \
  -d '{"inputs": {"query": "分析數據"}}'
```

然後查看日誌：

```bash
# 查看 Standalone 模式日誌
docker compose logs backend | grep -i "standalone\|invocation_mode" | tail -10
```

### 4. 測試 Plan Node Mode (Plan Path)

首先需要一個有效的 workspace_id，然後：

```bash
# 通過 workspace chat 觸發執行計劃（應該使用 plan_node 模式）
curl -X POST "http://localhost:8000/api/v1/workspaces/YOUR_WORKSPACE_ID/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "幫我分析數據並生成報告",
    "mode": "execution",
    "stream": false
  }'
```

查看日誌：

```bash
# 查看 Plan Node 模式日誌
docker compose logs backend | grep -i "plan_node\|plan_id\|task_id" | tail -10
```

### 5. 實時監控日誌

```bash
# 實時查看所有相關日誌
docker compose logs -f backend | grep -i "standalone\|plan_node\|invocation_mode\|context_mode"
```

### 6. 檢查策略路由

在容器內執行：

```bash
python -c "
import asyncio
import sys
sys.path.insert(0, '/app/backend')

from backend.app.services.playbook_run_executor import PlaybookRunExecutor
from backend.app.models.playbook import PlaybookInvocationContext, InvocationMode, InvocationStrategy

async def test():
    executor = PlaybookRunExecutor()

    # 測試 standalone 路由
    ctx_standalone = PlaybookInvocationContext(
        mode=InvocationMode.STANDALONE,
        strategy=InvocationStrategy(max_lookup_rounds=3),
        trace_id='test-standalone'
    )
    print(f'Standalone context created: {ctx_standalone.mode}')

    # 測試 plan_node 路由
    ctx_plan = PlaybookInvocationContext(
        mode=InvocationMode.PLAN_NODE,
        plan_id='test-plan',
        strategy=InvocationStrategy(max_lookup_rounds=1),
        trace_id='test-plan'
    )
    print(f'Plan Node context created: {ctx_plan.mode}, plan_id={ctx_plan.plan_id}')

asyncio.run(test())
"
```

## 預期日誌輸出

### Standalone Mode 應該看到：

```
PlaybookRunExecutor: playbook_code=data_analysis, execution_mode=conversation, context_mode=standalone
PlaybookRunExecutor: Executing data_analysis in STANDALONE mode (max_lookup_rounds=3)
PlaybookRunExecutor: Executing conversation in standalone mode (max_lookup_rounds=3)
```

### Plan Node Mode 應該看到：

```
PlaybookRunExecutor: playbook_code=data_analysis, execution_mode=conversation, context_mode=plan_node
PlaybookRunExecutor: Executing data_analysis in PLAN_NODE mode (plan_id=xxx, task_id=xxx)
PlaybookRunExecutor: Plan context available - summary=xxx, dependencies=xxx
```

## 驗證檢查清單

- [ ] Context 創建正常（✅ 已通過）
- [ ] Standalone 模式正確路由
- [ ] Plan Node 模式正確路由
- [ ] 日誌顯示正確的模式信息
- [ ] 兩種模式可以共存

## 除錯命令

```bash
# 查看完整執行日誌
docker compose logs backend --tail 100

# 查看特定 playbook 的執行
docker compose logs backend | grep "data_analysis"

# 查看錯誤
docker compose logs backend | grep -i "error\|exception\|traceback"
```
