---
playbook_code: yogacoach_plan_and_quota_guard
version: 1.0.0
locale: zh-TW
name: "方案配額檢查與扣減"
description: "檢查配額、預扣配額、結算配額、回滾配額，支援計費分鐘計算"
capability_code: yogacoach
tags:
  - yoga
  - quota
  - billing
---

# Playbook: 方案配額檢查與扣減

**Playbook Code**: `yogacoach_plan_and_quota_guard`
**版本**: 1.0.0
**用途**: 檢查配額、預扣配額、結算配額、回滾配額，支援計費分鐘計算

---

## 輸入資料

**注意**：`tenant_id`、`plan_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "action": "check",
  "resource_request": {
    "estimated_billable_minutes": 15,
    "actual_video_minutes": 15,
    "analysis_sampling_minutes": 15
  }
}
```

## 輸出資料

```json
{
  "quota_snapshot": {
    "remaining_minutes": 45,
    "plan_limit": 60,
    "used_minutes": 15
  },
  "allowed": true,
  "reservation_id": "reservation-abc123"
}
```

## 執行步驟

1. **檢查配額**（action: check）
   - 查詢當前配額使用情況
   - 檢查剩餘配額是否足夠
   - 返回配額快照

2. **預扣配額**（action: reserve）
   - 預扣預計使用的配額
   - 生成 reservation_id
   - 設置 TTL（超時自動釋放）

3. **結算配額**（action: commit）
   - 根據實際分析分鐘數結算配額
   - 從 segments 計算實際 billable_minutes
   - 釋放 reservation

4. **回滾配額**（action: rollback）
   - 釋放預扣的配額
   - 標記 reservation 為已回滾

## 能力依賴

- `yogacoach.plan_quota_guard`: 配額管理

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 計費分鐘計算

- 計費用 `billable_minutes`（= 分析段落總秒數/60），非視頻原始分鐘數
- 從 segments 計算實際分析分鐘數

## 錯誤處理

- 配額不足：返回錯誤，建議升級方案
- 配額檢查失敗：返回錯誤，記錄日誌

