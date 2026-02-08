---
playbook_code: yogacoach_retention_loop
version: 1.0.0
locale: zh-TW
name: "用戶留存與回訪"
description: "每週摘要、練習提醒、連續練習 streak、老師端班級總覽"
capability_code: yogacoach
tags:
  - yoga
  - retention
  - engagement
---

# Playbook: 用戶留存與回訪

**Playbook Code**: `yogacoach_retention_loop`
**版本**: 1.0.0
**用途**: 每週摘要、練習提醒、連續練習 streak、老師端班級總覽

---

## 輸入資料

**注意**：`tenant_id`、`user_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "trigger": "weekly_digest",
  "digest_config": {
    "include_trends": true,
    "include_next_plan": true,
    "include_streak": true
  },
  "frequency_control": {
    "max_pushes_per_week": 3,
    "allow_unsubscribe": true
  }
}
```

## 輸出資料

```json
{
  "nudge_plan": {
    "user_id": "user-123",
    "nudge_type": "weekly_digest",
    "scheduled_at": "2025-12-25T10:00:00Z",
    "channel": "line"
  },
  "weekly_digest": {
    "period": {
      "start_date": "2025-12-18",
      "end_date": "2025-12-24"
    },
    "summary": {
      "sessions_completed": 3,
      "total_minutes": 45,
      "improvement_highlights": [
        "對稱性提升 12%",
        "穩定度保持在 85 以上"
      ]
    },
    "next_week_plan": {
      "recommended_asanas": ["warrior_ii", "triangle_pose"],
      "goal": "提升平衡和對稱性"
    },
    "streak_status": {
      "current_streak": 7,
      "best_streak": 14,
      "achievement": "🔥 連續 7 天練習！"
    }
  }
}
```

## 執行步驟

1. **檢查推送頻率**
   - 檢查本週已推送次數
   - 如果超過 max_pushes_per_week，跳過推送

2. **檢查退訂狀態**
   - 檢查用戶是否已退訂
   - 如果已退訂，跳過推送

3. **生成每週摘要**
   - 從 E1 (Progress State Store) 獲取趨勢數據
   - 生成 improvement_highlights
   - 生成 next_week_plan

4. **計算 Streak**
   - 計算連續練習天數
   - 生成 achievement 訊息

5. **生成推送內容**
   - 根據 trigger 類型生成對應內容
   - weekly_digest: 每週摘要
   - practice_reminder: 練習提醒
   - achievement: 成就通知

6. **調用 C2 (Channel Delivery)**
   - 推送內容到指定渠道
   - 記錄推送狀態

## 能力依賴

- `yogacoach.retention_manager`: 留存管理
- `yogacoach.progress_tracker`: 進展追蹤（獲取趨勢數據）
- `yogacoach.channel_delivery`: 渠道推送

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 頻率限制與退訂

- **max_pushes_per_week**: 默認每週最多 3 次推送
- **allow_unsubscribe**: 必須提供退訂連結（尤其 LINE，被大量封鎖會廢掉渠道）
- **unsubscribe tracking**: 記錄退訂狀態到 `user_channels.push_enabled`

## 錯誤處理

- 推送頻率超限：跳過推送，記錄日誌
- 已退訂：跳過推送，記錄日誌
- 推送失敗：記錄錯誤，觸發重試

