---
playbook_code: yoga_coach_mapping
version: 1.0.0
locale: zh-TW
name: "老師示範對位與導覽"
description: "把事件對位到老師示範影片的章節，讓使用者看到「那一秒」"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: 老師示範對位與導覽

**Playbook Code**: `yoga_coach_mapping`
**版本**: 1.0.0
**用途**: 把事件對位到老師示範影片的章節，讓使用者看到「那一秒」

---

## 輸入資料

```json
{
  "priority_events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5,
      "event_id": "evt_001"
    }
  ],
  "asana_id": "downward_dog",
  "teacher_demo_video": {
    "youtube_id": "abc123xyz_downward_dog",
    "chapters": [
      {
        "name": "common_mistakes",
        "start": 75,
        "end": 150,
        "error_tags": ["knee_hyperextension", "rounded_back"]
      }
    ]
  },
  "segment_id": "seg_001"
}
```

---

## 處理步驟

### Step 1: 事件與章節對位

將優先事件對位到老師示範影片的章節：
- 檢查事件的 `type` 是否在章節的 `error_tags` 中
- 檢查章節名稱是否與事件相關（common_mistakes, modifications, alignment）
- 如果找到匹配章節，選擇最相關的章節
- 如果沒有匹配，使用預設章節（common_mistakes 或 alignment_points）

### Step 2: 生成 YouTube 時間碼連結

為每個播放列表項目生成 YouTube 連結：
- 格式：`https://youtube.com/watch?v={youtube_id}&t={start_time}s`
- 包含開始時間和結束時間
- 計算觀看時長（watch_duration）

### Step 3: 添加修改章節

如果播放列表未滿（最多 5 項），添加修改章節：
- 尋找 `modifications_beginner` 或 `modifications` 章節
- 添加到播放列表末尾

### Step 4: 生成播放列表

編譯完整的播放列表：
- 包含所有章節項目
- 計算總觀看時長
- 包含章節上下文和描述

---

## 輸出資料

```json
{
  "segment_id": "seg_001",
  "asana_id": "downward_dog",
  "teacher_demo_video": "abc123xyz_downward_dog",
  "playlist": [
    {
      "sequence": 1,
      "event_id": "evt_001",
      "chapter": "common_mistakes",
      "start_time": 75,
      "end_time": 150,
      "youtube_link": "https://youtube.com/watch?v=abc123xyz_downward_dog&t=75s",
      "reason": "示範Knee angle in yellow zone的調整方法",
      "watch_duration": 75,
      "context": {
        "zh-TW": "常見錯誤示範",
        "en": "Common mistakes"
      },
      "description": {
        "zh-TW": "常見的錯誤動作與調整方法",
        "en": "Common errors and how to fix them"
      }
    },
    {
      "sequence": 2,
      "chapter": "modifications_beginner",
      "start_time": 150,
      "end_time": 210,
      "youtube_link": "https://youtube.com/watch?v=abc123xyz_downward_dog&t=150s",
      "reason": "示範初階變化式",
      "watch_duration": 60
    }
  ],
  "total_watch_time": 135,
  "total_items": 2
}
```

### 決策邏輯

- 播放列表最多包含 5 個項目
- 優先顯示與事件相關的章節
- 如果沒有匹配章節，使用預設章節
- 自動添加修改章節（如果空間允許）

---

## 工具依賴

- `yogacoach.coach_mapping` - 老師示範對位工具
- `yogacoach.rubric_loader` - 載入 asana rubric（獲取 teacher_demo_video）

---

## 相關文檔

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) 第 5 節









