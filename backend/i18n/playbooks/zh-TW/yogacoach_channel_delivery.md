---
playbook_code: yogacoach_channel_delivery
version: 1.0.0
locale: zh-TW
name: "多渠道結果推送"
description: "將分析結果推送到 Web/LINE 渠道，支援 Flex Message 和降級策略"
capability_code: yogacoach
tags:
  - yoga
  - channel
  - delivery
---

# Playbook: 多渠道結果推送

**Playbook Code**: `yogacoach_channel_delivery`
**版本**: 1.0.0
**用途**: 將分析結果推送到 Web/LINE 渠道，支援 Flex Message 和降級策略

---

## 輸入資料

**注意**：`tenant_id`、`user_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "channel": "line",
  "delivery_bundle": {
    "main_card": {},
    "playlists": [],
    "share_link": {}
  },
  "channel_config": {
    "line": {
      "user_line_id": "U1234567890abcdef",
      "push_enabled": true
    },
    "web": {
      "email": "user@example.com",
      "notification_enabled": true
    }
  }
}
```

## 輸出資料

```json
{
  "delivered": true,
  "channel": "line",
  "channel_receipt": {
    "receipt_id": "receipt-abc123",
    "delivered_at": "2025-12-25T10:30:00Z",
    "delivery_method": "line_flex",
    "status": "success"
  },
  "fallback_used": false,
  "result_url": "https://yogacoach.app/s/abc12345"
}
```

## 執行步驟

1. **驗證渠道綁定**
   - 檢查 channel bind 狀態
   - 檢查退訂狀態
   - 如果未綁定或已退訂，返回錯誤

2. **生成推送內容**
   - Web: 生成結果頁面 URL
   - LINE: 生成 Flex Message 卡片

3. **推送結果**
   - Web: 發送 Email（可選）或生成通知
   - LINE: 通過 Push API 推送 Flex Message

4. **降級處理**
   - 如果 Flex Message 推送失敗，降級為簡單文字 + 連結
   - 記錄降級原因

5. **追蹤推送狀態**
   - 記錄推送狀態（success/failed/fallback_used）
   - 記錄推送時間和方式

6. **重試機制**
   - 如果推送失敗，記錄錯誤並觸發重試

## 能力依賴

- `yogacoach.channel_delivery`: 多渠道推送
- `yogacoach.line_push_service`: LINE 推送服務
- `yogacoach.channel_bind_validator`: 渠道綁定驗證

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 錯誤處理

- 渠道未綁定：返回錯誤，記錄日誌
- 已退訂：返回錯誤，記錄日誌
- 推送失敗：降級處理或返回錯誤，記錄日誌

