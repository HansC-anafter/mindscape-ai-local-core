# Runtime Profile 修复总结

## 更新日期
2025-12-29

## 修复内容

### 1. ✅ 事件写入修复（最高优先级）

**问题**：
- PolicyGuard/LoopBudget/QualityGates 事件没有真正写入 event_store
- 监控 API/Prometheus 会拿不到数据

**修复**：

#### 1.1 PolicyGuard 事件写入
- **文件**：`backend/app/services/playbook/tool_executor.py`
- **修复**：在调用 `PolicyGuard.check_tool_call` 时传递 `event_store`
- **变更**：
  ```python
  # 获取 event_store
  from backend.app.services.stores.events_store import EventsStore
  event_store = EventsStore(db_path=self.store.db_path)
  
  # 传递 event_store 给 PolicyGuard
  policy_result = policy_guard.check_tool_call(
      ...
      event_store=event_store
  )
  ```

#### 1.2 MultiAgentOrchestrator 事件写入
- **文件**：`backend/app/services/conversation/plan_executor.py`
- **修复**：
  1. 创建 MultiAgentOrchestrator 时传递 `event_store`、`workspace_id`、`profile_id`
  2. 在获取 `execution_id` 后更新 orchestrator 的 `execution_id` 属性
- **变更**：
  ```python
  # 获取 event_store
  from backend.app.services.stores.events_store import EventsStore
  db_path = getattr(self.tasks_store, 'db_path', None)
  event_store = EventsStore(db_path=db_path) if db_path else None
  
  # 创建 MultiAgentOrchestrator 时传递 event_store
  multi_agent_orchestrator = MultiAgentOrchestrator(
      ...
      workspace_id=workspace.id if workspace else None,
      profile_id=getattr(runtime_profile, 'profile_id', None),
      event_store=event_store
  )
  
  # 获取 execution_id 后更新
  if execution_id and multi_agent_orchestrator:
      multi_agent_orchestrator.execution_id = execution_id
  ```

#### 1.3 QualityGateChecker 事件写入
- **文件**：`backend/app/services/conversation/plan_executor.py`
- **修复**：创建 QualityGateChecker 时传递 `event_store`、`execution_id`、`profile_id`
- **变更**：
  ```python
  # 获取 event_store 和 execution_id
  from backend.app.services.stores.events_store import EventsStore
  db_path = getattr(self.tasks_store, 'db_path', None)
  event_store = EventsStore(db_path=db_path) if db_path else None
  
  execution_id_for_quality = None
  if results.get("executed_tasks"):
      first_task = results["executed_tasks"][0]
      if isinstance(first_task, dict):
          execution_id_for_quality = first_task.get("execution_id")
  
  # 创建 QualityGateChecker 时传递参数
  quality_checker = QualityGateChecker(
      workspace_id=workspace.id if workspace else None,
      project_path=None,
      execution_id=execution_id_for_quality,
      profile_id=getattr(runtime_profile, 'profile_id', None) if runtime_profile else None,
      event_store=event_store
  )
  ```

### 2. ✅ 预设模板字段名修复

**问题**：
- `require_explicit_approval` 字段不存在，实际会落回默认 `require_explicit_confirm=True`
- `routing_rules` 字段不存在，应该使用 `agent_routing_rules`

**修复**：
- **文件**：`backend/app/services/stores/runtime_profile_presets.py`
- **变更**：
  1. 将所有 `require_explicit_approval` 改为 `require_explicit_confirm`
  2. 将所有 `routing_rules` 改为 `agent_routing_rules`
- **影响**：
  - Security preset: `require_explicit_confirm=True`（所有写入都需要确认）
  - Agile preset: `require_explicit_confirm=False`（最小确认）
  - Research preset: `require_explicit_confirm=False`（中等确认）
  - 所有 preset 的拓扑路由规则现在会正确写入

### 3. ✅ 工具注册库回填 Fallback

**问题**：
- 工具注册库的 `capability_code`/`risk_class` 未回填会触发硬阻断
- `_ensure_tables` 只加栏位没回填，老资料会是空字符串
- `PolicyGuard` 使用 `strict_mode=True`，会在 `capability_code` 缺失时直接拒绝

**修复**：
- **文件**：`backend/app/services/tool_policy_resolver.py`
- **修复**：在 `resolve_policy_info` 中处理空字符串情况
- **变更**：
  ```python
  # 处理空字符串（来自未迁移的老数据）
  if not capability_code or capability_code.strip() == "":
      # Fallback: 从 tool_id 推断
      parts = tool_id.split(".")
      capability_code = parts[0] if parts else "unknown"
      logger.warning(f"Tool {tool_id} missing capability_code (empty string), inferred: {capability_code}")
  
  if not risk_class or risk_class.strip() == "":
      # Fallback: 使用默认值
      risk_class = "unknown"
      logger.warning(f"Tool {tool_id} missing risk_class (empty string), using default: {risk_class}")
  ```

**效果**：
- 即使工具注册库中 `capability_code` 或 `risk_class` 是空字符串，也会通过 fallback 推断
- 避免升级后所有工具调用被硬阻断
- 建议后续运行 `migrate_tool_registry_for_runtime_profile.py` 进行数据回填

## 影响范围

### 监控和观测
- ✅ PolicyGuard 事件现在会写入 event_store
- ✅ LoopBudget 事件现在会写入 event_store
- ✅ QualityGates 事件现在会写入 event_store
- ✅ 监控 API/Prometheus 可以获取到数据

### 预设模板
- ✅ Security preset 的确认策略现在会正确生效
- ✅ Agile preset 的确认策略现在会正确生效
- ✅ Research preset 的确认策略现在会正确生效
- ✅ 所有 preset 的拓扑路由规则现在会正确写入

### 工具调用
- ✅ 老数据（空字符串）现在会通过 fallback 推断，不会硬阻断
- ✅ 建议运行迁移脚本进行数据回填

## 后续工作

1. **数据迁移**：运行 `migrate_tool_registry_for_runtime_profile.py` 回填工具注册库的 `capability_code` 和 `risk_class`
2. **验证**：检查监控 API 是否能够获取到 PolicyGuard/LoopBudget/QualityGates 事件
3. **测试**：验证预设模板的确认策略和拓扑路由规则是否正确生效

## 相关文件

- `backend/app/services/playbook/tool_executor.py`
- `backend/app/services/conversation/plan_executor.py`
- `backend/app/services/stores/runtime_profile_presets.py`
- `backend/app/services/tool_policy_resolver.py`
- `backend/app/services/conversation/policy_guard.py`
- `backend/app/services/orchestration/multi_agent_orchestrator.py`
- `backend/app/services/conversation/quality_gate_checker.py`

