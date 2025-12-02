---
playbook_code: weekly_review_onboarding
version: 1.0.0
locale: zh-TW
name: 本週工作節奏（冷啟動版）
description: 冷啟動專用：快速了解用戶的工作習慣與節奏
tags:
  - onboarding
  - planning
  - work-rhythm
  - cold-start

kind: user_workflow
interaction_mode:
  - conversational
  - needs_review
visible_in:
  - workspace_tools_panel
  - workspace_playbook_menu

language_strategy: model_native
locale: zh-TW
supported_locales:
  - zh-TW
  - en
default_locale: zh-TW
auto_localize: true

entry_agent_type: planner
onboarding_task: task3
icon: ⏰
required_tools: []
scope:
  visibility: system
  editable: false
owner:
  type: system
---

# 本週工作節奏 - 冷啟動 SOP

## 目標
快速了解用戶的工作習慣、常用工具、時間節奏，並自動提取工作模式種子，完成冷啟動流程。

## 個性化調整

### 使用用戶的開局角色卡
根據用戶在任務 1 填寫的內容：
- **現在在做**：{self_description.identity}
- **想搞定的**：{self_description.solving}

用這些信息來調整問題的角度和例子。

## 執行步驟

### 開場白
```
最後一個暖機任務了！🎯

想更了解你的工作習慣，這樣之後幫你規劃任務時會更配合你的節奏。

聊 3 個問題就好，不會花很久 😊
```

### 問題 1：這週要做的事

**提問方式**
```
這週你打算做哪 3 件事？
（專案、任務、會議、個人目標都算，就說你心裡排的）
```

**追問（可選）**
如果用戶說得很簡略，可以追問：
```
好的，那這 3 件事裡，哪一件你覺得最重要/最想先搞定？
```

**要提取的信息：**
- 任務類型（技術開發 / 內容創作 / 會議溝通 / 學習...）
- 優先級判斷模式
- 任務粒度（大專案 vs 小任務）

### 問題 2：常用工具

**提問方式**
```
你平常用什麼工具工作？

比如：
• WordPress / Notion / Google Docs（寫作 / 筆記）
• GitHub / GitLab（程式碼）
• Figma / Sketch（設計）
• 其他你常用的...

隨便說幾個就好 👍
```

**要提取的信息：**
- 工具類別（CMS / 筆記 / 程式碼 / 設計 / 專案管理）
- 工具組合（判斷工作流程）
- 雲端 vs 本地偏好

### 問題 3：工作節奏偏好

**提問方式（選擇題 + 自由回答）**
```
你比較喜歡什麼樣的工作節奏？

可以選一個，或直接說你的習慣：

A. 早上集中精力處理重要任務
B. 晚上比較有靈感，適合深度工作
C. 喜歡一次專注一件事，完成再換下一個
D. 喜歡多工切換，同時推進多個任務
E. 其他：（自己說）

或是你有其他工作節奏的偏好？
```

**追問（如果用戶選了 A 或 B）**
```
那你通常幾點開始工作 / 幾點比較有狀態？
```

**要提取的信息：**
- 時間偏好（早晨型 / 夜貓型）
- 任務處理模式（專注型 / 多工型）
- 工作時段（幾點到幾點）

### 步驟 4: 完成總結

```
好的！我記住了 📝

你的工作節奏：
• 本週重點：{weekly_tasks}
• 常用工具：{tools}
• 偏好時段：{time_preference}
• 任務模式：{work_mode}

之後規劃任務時會配合你的習慣 👍

---

🎉 心智空間已完全啟動！

你已經完成了所有暖機任務：
✅ 任務 1：開局角色卡
✅ 任務 2：第一個長線任務
✅ 任務 3：本週工作節奏

之後每次你完成任務，系統都會從使用記錄中挖出新的線索，
再問你要不要「升級」這份心智空間。

[ 返回心智空間 ]  [ 直接開始一個任務 ]
```

## 輸出格式（機器可讀）

對話結束後，輸出 JSON 格式供系統處理：

```json
{
  "onboarding_task": "task3",
  "work_rhythm_data": {
    "weekly_tasks": [
      {
        "task": "任務 1",
        "type": "development",
        "priority": "high",
        "estimated_hours": 10
      }
    ],
    "tools": [
      {
        "name": "WordPress",
        "category": "cms",
        "usage_frequency": "daily"
      },
      {
        "name": "Notion",
        "category": "notes",
        "usage_frequency": "daily"
      }
    ],
    "time_preferences": {
      "preferred_time": "morning",
      "work_start": "09:00",
      "peak_hours": "09:00-12:00",
      "focus_duration": "2-3 hours"
    },
    "work_mode": {
      "style": "focused",
      "multitasking": false,
      "break_frequency": "every_2_hours",
      "context_switching_tolerance": "low"
    }
  },
  "extracted_seeds": [
    {
      "seed_type": "preference",
      "seed_text": "偏好早上集中精力處理重要任務",
      "confidence": 0.8
    },
    {
      "seed_type": "preference",
      "seed_text": "喜歡一次專注一件事，完成再換下一個",
      "confidence": 0.9
    },
    {
      "seed_type": "entity",
      "seed_text": "WordPress",
      "metadata": {
        "category": "tool",
        "usage": "daily"
      },
      "confidence": 1.0
    },
    {
      "seed_type": "entity",
      "seed_text": "Notion",
      "metadata": {
        "category": "tool",
        "usage": "daily"
      },
      "confidence": 1.0
    }
  ]
}
```

## 與心智空間的銜接

1. **創建工作模式種子**
   - 使用 `extracted_seeds` 寫入 `mindscape_seed_log`
   - 標記來源為 `onboarding_task3`

2. **更新冷啟動狀態**
   - 調用 `/api/v1/mindscape/onboarding/complete-task3`
   - 傳入 `execution_id` 和 `created_seeds_count`

3. **觸發恭喜訊息**
   - 前端檢測到 3/3 完成
   - 顯示恭喜 Banner

## 語氣與風格

- ✅ 輕鬆、像朋友聊天（「聊 3 個問題」）
- ✅ 給選項，降低思考負擔
- ✅ 快速完成（3-5 分鐘）
- ✅ 明確慶祝完成（🎉 + confetti）

## 成功標準

- AI 了解用戶的工作時間偏好
- AI 知道用戶常用的工具
- AI 知道用戶的任務處理模式（專注 vs 多工）
- 自動創建了 4-6 個工作模式種子
- 冷啟動進度更新為 3/3（完成）
- 觸發恭喜訊息
