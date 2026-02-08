# Runtime Profile API 使用指南

## 概述

Runtime Profile API 允许您配置工作区的执行契约、交互预算、输出契约、确认政策和工具政策。这些配置决定了 AI 助手在工作区中的行为方式。

## 基础概念

### Runtime Profile 是什么？

Runtime Profile（运行时配置文件）定义了工作区的执行契约，包括：

- **执行模式**：QA、Execution 或 Hybrid
- **交互预算**：每轮最多询问次数、是否假设默认值
- **输出契约**：代码风格、写作风格、解释详细程度
- **确认政策**：哪些操作需要用户确认
- **工具政策**：允许/禁止的工具列表

### 存储方式

- **MVP 阶段**：存储在 `workspace.metadata['runtime_profile']`（JSON 格式）
- **未来版本**：可能迁移到独立数据库表

## API 端点

### 1. 获取 Runtime Profile

**GET** `/api/v1/workspaces/{workspace_id}/runtime-profile`

获取工作区的运行时配置文件。

**请求示例：**
```bash
curl -X GET "https://api.example.com/api/v1/workspaces/ws_123/runtime-profile" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**响应示例：**
```json
{
  "default_mode": "execution",
  "interaction_budget": {
    "max_questions_per_turn": 0,
    "assume_defaults": true,
    "require_assumptions_list": true
  },
  "output_contract": {
    "coding_style": "patch_first",
    "writing_style": "structure_first",
    "minimize_explanation": true,
    "show_rationale_level": "brief",
    "include_decision_log": false
  },
  "confirmation_policy": {
    "auto_read": true,
    "confirm_soft_write": true,
    "confirm_external_write": true,
    "confirmation_format": "list_changes",
    "require_explicit_confirm": true
  },
  "tool_policy": {
    "allowlist": ["code_editor", "file_manager"],
    "denylist": null,
    "require_approval_for_capabilities": [],
    "allow_parallel_tool_calls": false,
    "max_tool_call_chain": 5
  },
  "schema_version": "2.0",
  "updated_by": "user_456",
  "updated_reason": "Enable Cursor-style execution",
  "created_at": "2025-12-28T10:00:00Z",
  "updated_at": "2025-12-29T15:30:00Z"
}
```

**说明：**
- 如果工作区没有配置 Runtime Profile，将返回默认配置
- 默认配置使用标准设置（`execution_mode: "qa"`, `max_questions_per_turn: 2`）

---

### 2. 更新 Runtime Profile

**PUT** `/api/v1/workspaces/{workspace_id}/runtime-profile`

更新或创建工作区的运行时配置文件。

**请求示例：**
```bash
curl -X PUT "https://api.example.com/api/v1/workspaces/ws_123/runtime-profile?updated_by=user_456&updated_reason=Enable%20Cursor-style%20execution" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "default_mode": "execution",
    "interaction_budget": {
      "max_questions_per_turn": 0,
      "assume_defaults": true,
      "require_assumptions_list": true
    },
    "output_contract": {
      "coding_style": "patch_first",
      "minimize_explanation": true,
      "show_rationale_level": "brief"
    },
    "confirmation_policy": {
      "auto_read": true,
      "confirm_external_write": true,
      "confirmation_format": "list_changes"
    },
    "tool_policy": {
      "allowlist": ["code_editor", "file_manager"]
    }
  }'
```

**查询参数：**
- `updated_by` (可选)：更新者的用户 ID
- `updated_reason` (可选)：更新原因（用于审计）

**重要提示：**
- ⚠️ **不支持部分更新**：必须提供完整的 Runtime Profile 配置
- 建议先使用 `GET` 获取当前配置，修改后再使用 `PUT` 更新

---

### 3. 删除 Runtime Profile

**DELETE** `/api/v1/workspaces/{workspace_id}/runtime-profile`

删除工作区的运行时配置文件。

**请求示例：**
```bash
curl -X DELETE "https://api.example.com/api/v1/workspaces/ws_123/runtime-profile" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**响应：**
- 成功：HTTP 204 No Content
- 失败：HTTP 404 Not Found（配置文件不存在）

**警告：**
- ⚠️ 此操作**不可撤销**
- 删除后，工作区将恢复默认行为
- 建议在删除前备份配置

---

### 4. 获取预设模板列表

**GET** `/api/v1/workspaces/runtime-profile/presets`

获取可用的预设模板列表。

**请求示例：**
```bash
curl -X GET "https://api.example.com/api/v1/workspaces/runtime-profile/presets" \
  -H "Authorization: Bearer YOUR_TOKEN"
```

**响应示例：**
```json
{
  "presets": [
    {
      "name": "security",
      "label": "安全模板",
      "description": "嚴格確認政策、完整品質關卡、保守工具政策",
      "icon": "🛡️"
    },
    {
      "name": "agile",
      "label": "敏捷模板",
      "description": "最小確認、快速執行、寬鬆工具政策",
      "icon": "⚡"
    },
    {
      "name": "research",
      "label": "研究模板",
      "description": "詳細輸出、引用要求、完整決策日誌",
      "icon": "🔬"
    }
  ]
}
```

---

### 5. 应用预设模板

**POST** `/api/v1/workspaces/{workspace_id}/runtime-profile/apply-preset`

将预设模板应用到工作区。

**请求示例：**
```bash
curl -X POST "https://api.example.com/api/v1/workspaces/ws_123/runtime-profile/apply-preset?updated_by=user_456&updated_reason=Setting%20up%20development%20workspace" \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "preset_name": "agile"
  }'
```

**请求体：**
```json
{
  "preset_name": "agile"  // 或 "security" 或 "research"
}
```

**查询参数：**
- `updated_by` (可选)：应用预设的用户 ID
- `updated_reason` (可选)：应用预设的原因

**响应示例：**
```json
{
  "default_mode": "execution",
  "interaction_budget": {
    "max_questions_per_turn": 0,
    "assume_defaults": true
  },
  // ... 其他配置
}
```

---

## 预设模板说明

### Security（安全模板）🛡️

**适用场景：**
- 生产环境
- 敏感数据工作区
- 需要严格控制的场景

**配置特点：**
- 严格确认政策（所有写入操作都需要确认）
- 完整品质关卡（lint、tests、docs 必须通过）
- 保守工具政策（仅允许必要的工具）

### Agile（敏捷模板）⚡

**适用场景：**
- 开发环境
- 快速迭代
- 实验性工作

**配置特点：**
- 最小确认（仅外部写入需要确认）
- 快速执行（不询问问题，自动假设默认值）
- 宽松工具政策（允许大多数工具）

### Research（研究模板）🔬

**适用场景：**
- 研究项目
- 文档编写
- 需要详细输出的场景

**配置特点：**
- 详细输出（完整决策日志）
- 引用要求（必须包含引用）
- 完整决策日志（包含假设、风险、下一步）

---

## 最佳实践

### 1. 使用预设模板作为起点

```bash
# 1. 获取可用预设
GET /api/v1/workspaces/runtime-profile/presets

# 2. 应用预设
POST /api/v1/workspaces/{workspace_id}/runtime-profile/apply-preset
{
  "preset_name": "agile"
}

# 3. 根据需要自定义
PUT /api/v1/workspaces/{workspace_id}/runtime-profile
{
  // 基于预设的完整配置，加上自定义修改
}
```

### 2. 渐进式配置

不要一次性配置所有选项，建议：

1. **第一步**：应用预设模板
2. **第二步**：测试基本功能
3. **第三步**：根据实际需求微调
4. **第四步**：记录配置变更原因

### 3. 配置变更管理

- 使用 `updated_by` 和 `updated_reason` 记录变更
- 在开发环境测试后再应用到生产环境
- 定期备份重要配置

### 4. 常见配置模式

#### Cursor 风格（快速执行）

```json
{
  "default_mode": "execution",
  "interaction_budget": {
    "max_questions_per_turn": 0,
    "assume_defaults": true,
    "require_assumptions_list": true
  },
  "output_contract": {
    "coding_style": "patch_first",
    "minimize_explanation": true,
    "show_rationale_level": "brief"
  }
}
```

#### 编辑风格（详细输出）

```json
{
  "default_mode": "hybrid",
  "interaction_budget": {
    "max_questions_per_turn": 2
  },
  "output_contract": {
    "writing_style": "structure_first",
    "show_rationale_level": "detailed",
    "include_decision_log": true
  }
}
```

#### 研究风格（完整记录）

```json
{
  "default_mode": "qa",
  "interaction_budget": {
    "max_questions_per_turn": 5
  },
  "output_contract": {
    "show_rationale_level": "detailed",
    "include_decision_log": true
  },
  "quality_gates": {
    "require_citations": true
  }
}
```

---

## 错误处理

### 常见错误码

| HTTP 状态码 | 说明 | 解决方案 |
|------------|------|---------|
| 400 | 无效的配置 | 检查请求体格式和字段值 |
| 404 | 工作区或配置文件不存在 | 确认工作区 ID 正确 |
| 500 | 服务器内部错误 | 联系技术支持 |

### 错误响应示例

```json
{
  "detail": "Invalid preset name: invalid_preset. Available presets: security, agile, research"
}
```

---

## 版本兼容性

### Schema 版本

Runtime Profile 使用 `schema_version` 字段管理版本兼容性：

- **1.0**：MVP 版本（5 个核心字段）
- **2.0**：Phase 2 版本（包含 loop_budget, stop_conditions, quality_gates 等）

### 向后兼容

- 旧版本配置会自动迁移到新版本
- 新版本字段在旧版本中会被忽略
- 建议始终使用最新版本的 API

---

## 相关文档

- [Runtime Profile 架构评估](../implementation/workspace-runtime-profile-architecture-assessment-2025-12-28.md)
- [Runtime Profile 缺口分析](../implementation/workspace-runtime-profile-gap-analysis-2025-12-29.md)
- [PolicyGuard 使用指南](../services/policy-guard-guide.md)

---

**最后更新：** 2025-12-29
**API 版本：** v1





