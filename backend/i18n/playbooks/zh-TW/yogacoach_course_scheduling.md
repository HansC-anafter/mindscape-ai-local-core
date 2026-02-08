---
playbook_code: yogacoach_course_scheduling
version: 1.0.0
locale: zh-TW
name: "課程排課與預約管理"
description: "課程表同步、課程創建/編輯/取消、預約管理、候補名單管理、課程異動通知"
capability_code: yogacoach
tags:
  - yoga
  - course
  - scheduling
---

# Playbook: 課程排課與預約管理

**Playbook Code**: `yogacoach_course_scheduling`
**版本**: 1.0.0
**用途**: 課程表同步、課程創建/編輯/取消、預約管理、候補名單管理、課程異動通知

---

## 輸入資料

**注意**：`tenant_id`、`teacher_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "action": "book",
  "class_info": {
    "class_id": "class-abc123",
    "title": "初級流瑜伽",
    "datetime": "2025-12-25T10:00:00Z",
    "duration_minutes": 60
  },
  "booking_info": {
    "user_id": "user-123"
  }
}
```

## 輸出資料

```json
{
  "class_info": {
    "class_id": "class-abc123",
    "status": "scheduled",
    "booking_url": "https://yogacoach.app/book/class-abc123",
    "students": [
      {
        "user_id": "user-123",
        "name": "張三",
        "booking_status": "confirmed"
      }
    ]
  },
  "booking_result": {
    "booking_id": "booking-xyz789",
    "status": "confirmed",
    "payment_url": "https://yogacoach.app/pay/abc12345",
    "confirmation_sent": true
  }
}
```

## 執行步驟

1. **課程操作**（action: create_class/update_class/cancel_class）
   - 創建/編輯/取消課程
   - 同步到外部排課系統（Google Calendar/Calendly/MindBody）

2. **預約管理**（action: book/cancel_booking）
   - 檢查課程容量
   - 創建預約記錄
   - 生成支付連結（如需要）

3. **候補名單管理**
   - 如果課程已滿，加入候補名單
   - 有空位時自動通知候補學員

4. **課程異動通知**
   - 調用 C2 (Channel Delivery) 推送課程異動通知
   - 發送 Email 通知（可選）

## 能力依賴

- `yogacoach.course_scheduler`: 課程排課
- `yogacoach.calendar_sync`: 日曆同步
- `yogacoach.channel_delivery`: 渠道推送（課程異動通知）

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 錯誤處理

- 課程已滿：返回錯誤，加入候補名單
- 預約失敗：返回錯誤，記錄日誌
- 同步失敗：返回錯誤，記錄日誌

