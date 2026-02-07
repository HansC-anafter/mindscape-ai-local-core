---
playbook_code: moltbot_deep_task
version: "1.0"
kind: workflow
description: 使用 Moltbot 在 Mindscape 治理下執行深度自動化任務
governance:
  risk_level: high
  requires_approval: true
  sandbox_required: true
inputs:
  task_description:
    type: string
    required: true
    description: 要執行的任務描述
  allowed_skills:
    type: array
    default: ["file", "web_search"]
    description: 允許 Moltbot 使用的技能
  max_duration:
    type: integer
    default: 300
    description: 最大執行時間（秒）
---

# Moltbot 深度任務執行

使用 Moltbot 在 Mindscape 治理層控制下執行複雜自動化任務。

## 使用場景

- 需要深度檔案操作的自動化任務
- 需要多步驟連續執行的工作流
- 需要保留完整執行軌跡的任務

## 治理保障

1. **Sandbox 隔離**：Moltbot 只能存取指定的 Sandbox 目錄
2. **技能白名單**：只允許指定的技能執行
3. **執行超時**：強制限制最大執行時間
4. **軌跡記錄**：所有操作記錄到 Asset Provenance

## 執行步驟

### Step 1: Preflight 檢查

```yaml
id: preflight
tool: governance.agent_preflight
inputs:
  task: "{{input.task_description}}"
  allowed_skills: "{{input.allowed_skills}}"
  sandbox_path: "{{context.sandbox_path}}"
```

驗證任務是否符合治理政策：
- 檢查危險命令模式
- 驗證 Sandbox 路徑
- 評估風險等級

### Step 2: 人工確認（高風險時）

```yaml
id: human_approval
tool: governance.request_approval
depends_on: ["preflight"]
condition: "{{step.preflight.requires_human_approval}}"
inputs:
  message: "即將執行高風險任務，請確認"
  task_preview: "{{input.task_description}}"
  risk_level: "{{step.preflight.risk_level}}"
```

### Step 3: 執行 Moltbot

```yaml
id: execute
tool: external_agent.moltbot_execute
depends_on: ["preflight", "human_approval?"]
inputs:
  task: "{{input.task_description}}"
  allowed_skills: "{{input.allowed_skills}}"
  max_duration: "{{input.max_duration}}"
governance:
  checkpoint: true
```

在隔離 Sandbox 內執行任務，收集執行軌跡。

### Step 4: 記錄 Provenance

```yaml
id: record
tool: provenance.record_take
depends_on: ["execute"]
inputs:
  execution_trace: "{{step.execute.execution_trace}}"
  intent_ref: "{{context.intent_id}}"
  lens_ref: "{{context.lens_id}}"
  success: "{{step.execute.success}}"
```

將執行結果記錄為 Take，連結到當前 Intent 和 Lens。

## 輸出

- `success`: 執行是否成功
- `output`: Moltbot 產出內容
- `files_created`: 新建的檔案列表
- `files_modified`: 修改的檔案列表
- `execution_id`: 執行追蹤 ID（供回溯查詢）

## 注意事項

> [!CAUTION]
> 此 Playbook 啟用外部 Agent 執行，請確保：
> 1. 任務描述不含危險命令
> 2. 已審核允許的技能列表
> 3. 理解執行可能產生的副作用

## 相關文件

- [Asset Provenance Architecture](file:///docs/core-architecture/asset-provenance.md)
- [External Agent Integration](file:///docs/core-architecture/external-agents.md)
