---
playbook_code: yogacoach_intake_router
version: 1.0.0
locale: zh-TW
name: "會話建立與路由"
description: "服務入口，建立 session_id，綁定 user_id、teacher_id、plan_id，識別渠道，檢查配額，決定上傳方式"
capability_code: yogacoach
tags:
  - yoga
  - intake
  - routing
---

# Playbook: 會話建立與路由

**Playbook Code**: `yogacoach_intake_router`
**版本**: 1.0.0
**用途**: 服務入口，建立 session_id，綁定 user_id、teacher_id、plan_id，識別渠道，檢查配額，決定上傳方式

---

## 輸入資料

**注意**：`tenant_id`、`actor_id`、`subject_user_id`、`plan_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "teacher_id": "teacher-789",
  "channel": "web",
  "liff_context": {
    "line_user_id": "U1234567890abcdef"
  }
}
```

## 輸出資料

```json
{
  "session_id": "session-abc123",
  "idempotency_key": "idemp-xyz789",
  "upload_policy": {
    "method": "frontend_keypoints",
    "max_duration_sec": 900,
    "allowed_formats": ["mp4", "mov"]
  },
  "quota_snapshot": {
    "remaining_minutes": 45,
    "plan_limit": 60
  }
}
```

## 執行步驟

1. **建立會話**
   - 調用 `yogacoach.intake_router` capability
   - 生成 `session_id` 和 `idempotency_key`
   - 綁定 `teacher_id`（`user_id`、`plan_id` 由 runtime 從 execution envelope 提供）

2. **識別渠道**
   - 檢查 `channel` 參數（web/line）
   - 如果是 LINE，提取 `liff_context` 中的 `line_user_id`

3. **檢查配額**
   - 調用 `yogacoach.plan_quota_guard` capability
   - 檢查剩餘配額是否足夠（`plan_id` 由 runtime 從 execution envelope 提供）
   - 返回配額快照

4. **決定上傳方式**
   - 根據渠道和配額決定上傳方式
   - `frontend_keypoints`: 前端提取 keypoints
   - `backend_video`: 後端處理視頻

5. **生成上傳策略**
   - 根據上傳方式生成對應的策略
   - 設置 TTL 和格式限制

## 能力依賴

- `yogacoach.intake_router`: 會話建立與路由
- `yogacoach.plan_quota_guard`: 配額檢查

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 錯誤處理

- 配額不足：返回錯誤，建議升級方案
- 渠道無效：返回錯誤，僅支援 web/line
- 會話建立失敗：返回錯誤，記錄日誌

