---
playbook_code: yogacoach_job_dispatcher
version: 1.0.0
locale: zh-TW
name: "任務派工與狀態追蹤"
description: "接收上傳完成通知，創建後台任務異步執行 7-playbook pipeline，提供任務狀態追蹤"
capability_code: yogacoach
tags:
  - yoga
  - job
  - pipeline
---

# Playbook: 任務派工與狀態追蹤

**Playbook Code**: `yogacoach_job_dispatcher`
**版本**: 1.0.0
**用途**: 接收上傳完成通知，創建後台任務異步執行 7-playbook pipeline，提供任務狀態追蹤

---

## 輸入資料

**注意**：`tenant_id`、`session_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "payload_type": "keypoints",
  "payload": {
    "keypoints_data": {}
  },
  "callback_config": {
    "channel": "web",
    "user_id": "user-123"
  },
  "pipeline_version": "v1.2.0"
}
```

## 輸出資料

```json
{
  "job_id": "job-abc123",
  "status": "queued",
  "status_url": "/api/yogacoach/jobs/job-abc123/status",
  "estimated_finish_time": "2025-12-25T10:30:00Z",
  "estimated_wait_seconds": 30,
  "idempotency_key": "idemp-xyz789"
}
```

## 執行步驟

1. **檢查冪等性**
   - 檢查 `(session_id, pipeline_version)` 是否已存在任務
   - 如果存在，返回已存在的 `job_id` 和狀態

2. **創建後台任務**
   - 生成 `job_id`（UUID）
   - 設置任務狀態為 `queued`
   - 記錄任務元數據（payload_type, callback_config, pipeline_version）

3. **預扣配額**
   - 調用 `yogacoach.plan_quota_guard` capability
   - 預扣預計使用的配額（基於 payload 估算）

4. **排隊執行**
   - 將任務加入執行隊列
   - 返回任務狀態和預估完成時間

5. **異步執行 Pipeline**
   - 調用 `pipeline_orchestrator.execute_pipeline()`
   - 執行核心 7 playbooks
   - 記錄實際分析分鐘數

6. **結算配額**
   - 根據實際分析分鐘數結算配額
   - 調用 `yogacoach.plan_quota_guard` capability 的 `commit_quota`

7. **回調通知**
   - 任務完成後調用 C2 (Channel Delivery) 推送結果
   - 失敗時記錄錯誤，觸發重試或降級

## 能力依賴

- `yogacoach.job_dispatcher`: 任務派工與狀態追蹤
- `yogacoach.plan_quota_guard`: 配額管理
- `yogacoach.pipeline_orchestrator`: Pipeline 執行

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## Exactly-once 保證

- `session_id` 全局唯一（PRIMARY KEY）
- `job_id` 全局唯一（PRIMARY KEY）
- `(session_id, pipeline_version)` 唯一索引（防止同一 session 用不同版本重複執行）
- Job Dispatcher 收到重複請求時，返回已存在的 `job_id` 和 `status_url`（不創建新任務）

## 錯誤處理

- 配額不足：返回錯誤，建議升級方案
- 任務創建失敗：返回錯誤，記錄日誌
- Pipeline 執行失敗：記錄錯誤，觸發重試或降級

