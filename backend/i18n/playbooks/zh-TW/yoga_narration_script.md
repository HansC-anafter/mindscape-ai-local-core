---
playbook_code: yoga_narration_script
version: 1.0.0
locale: zh-TW
name: "AI 講解腳本生成"
description: "生成「一次只講一件事」且不逼迫變好的講解文案"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: AI 講解腳本生成

**Playbook Code**: `yoga_narration_script`
**版本**: 1.0.0
**用途**: 生成「一次只講一件事」且不逼迫變好的講解文案

---

## 輸入資料

```json
{
  "allowed_actions": {
    "give_detailed_feedback": true,
    "suggest_progression": false,
    "suggest_modifications": true,
    "suggest_alternatives": true
  },
  "priority_events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5
    }
  ],
  "coach_playlist": {
    "playlist": [...]
  },
  "rubric": {
    "asana_code": "downward_dog",
    "modifications": {...}
  },
  "segment_id": "seg_001",
  "asana_name": "下犬式"
}
```

---

## 處理步驟

### Step 1: 選擇焦點點（只講 1-2 件事）

從優先事件中選擇最重要的 1-2 個事件：
- 優先順序：紅區 > 黃區
- 最多選擇 2 個焦點點（預設 1 個）
- 確保「一次只講一件事」的原則

### Step 2: 生成講解文案（瑜伽友善語氣）

為每個焦點事件生成講解文案：
- **observation**: 觀察描述（友善、不批判）
- **adjustment**: 調整建議（僅在 allowed_actions.give_detailed_feedback 為 true 時）
- **self_check**: 自我檢查提示（總是包含，培養身體覺察）
- **safety_note**: 安全提醒（黃/紅區事件時包含）

### Step 3: 生成替代路徑

根據 rubric 生成替代版本：
- **beginner**: 初階版本（如果有）
- **with_props**: 使用輔具版本（如果有）
- **rest**: 休息式（總是包含）

### Step 4: 生成螢幕提示

生成簡短的螢幕提示文字：
- 在動作保持期間顯示
- 只顯示焦點點文字
- 位置：中央

---

## 輸出資料

```json
{
  "segment_id": "seg_001",
  "main_feedback": {
    "focus_point": "膝蓋對位",
    "observation": "在下犬式中，你的Knee angle in yellow zone。",
    "adjustment": "試著微彎膝蓋，想像膝蓋正面朝向正前方，避免鎖死。",
    "self_check": "感受大腿後側是否有適度延伸，而不是膝蓋承受壓力。",
    "safety_note": "如果膝蓋感到不適，可以改為微彎膝蓋的版本。"
  },
  "alternative_paths": [
    {
      "path_type": "beginner",
      "description": "初階版本",
      "demo_link": "https://youtube.com/watch?v=abc123xyz&t=120s"
    },
    {
      "path_type": "with_props",
      "description": "使用yoga_block輔助",
      "demo_link": "https://youtube.com/watch?v=abc123xyz&t=150s"
    },
    {
      "path_type": "rest",
      "description": "休息式（孩童式）",
      "demo_link": null
    }
  ],
  "on_screen_cues": [
    {
      "timing": "during_hold",
      "text": "膝蓋對位",
      "position": "center"
    }
  ]
}
```

### 決策邏輯

- 如果沒有事件 → 生成一般性正面回饋
- 如果 allowed_actions.give_detailed_feedback 為 false → 不包含 adjustment
- 如果事件嚴重度為 red → 包含強烈的安全提醒
- 如果事件嚴重度為 yellow → 包含溫和的安全提醒

---

## 工具依賴

- `yogacoach.narration_script` - AI 講解腳本生成工具
- `yogacoach.rubric_loader` - 載入 asana rubric（獲取 modifications）

---

## 相關文檔

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) 第 6 節









