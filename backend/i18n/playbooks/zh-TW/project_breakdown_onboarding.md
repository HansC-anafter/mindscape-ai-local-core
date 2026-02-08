---
playbook_code: project_breakdown_onboarding
version: 1.0.0
capability_code: planning
locale: zh-TW
name: 第一個長線任務（冷啟動版）
description: 冷啟動專用：幫助新用戶快速拆解第一個想推進的專案
tags:
  - onboarding
  - planning
  - project
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
onboarding_task: task2
icon: 📋
required_tools: []
scope:
  visibility: system
  editable: false
owner:
  type: system
---

# 第一個長線任務 - 冷啟動 SOP

## 目標
幫助新用戶快速將「最想搞定的一件事」拆解成可執行的步驟，並自動創建第一張長線任務卡。

## 個性化調整

### 使用用戶的開局角色卡
根據用戶在任務 1 填寫的內容：
- **現在在做**：{self_description.identity}
- **想搞定的**：{self_description.solving}
- **在思考的**：{self_description.thinking}

用這些資訊來理解用戶的背景和需求，調整建議的角度。

## 執行步驟

### 開場白
```
我看到你想搞定的是「{self_description.solving}」，讓我幫你拆成可執行的步驟。

這個過程不會花很久，大概 3-5 分鐘就能完成 🚀
```

### 步驟 1: 理解專案核心（2 個問題）

**問題 1：詳細說說這件事**
```
先跟我說說「{self_description.solving}」具體是什麼？

你可以隨意描述，我會幫你整理出重點。
```

**問題 2：你希望達到什麼狀態？**
```
如果這件事搞定了，你期待看到什麼結果？
（不用很正式，就說你心裡想的狀態）
```

### 步驟 2: 快速拆解（AI 主動建議）

根據用戶的描述，**AI 主動提出 3-4 個關鍵步驟**：

```
好的！我幫你整理出了幾個關鍵步驟：

1. 【步驟 1 名稱】
   - 具體要做什麼
   - 為什麼這是第一步

2. 【步驟 2 名稱】
   - 具體要做什麼
   - 依賴步驟 1 的什麼

3. 【步驟 3 名稱】
   - 具體要做什麼
   - 這一步完成就差不多了

4. （可選）【步驟 4 名稱】
   - 如果需要的話...

這樣拆可以嗎？有想調整的地方嗎？
```

**用戶回饋處理：**
- 如果說「可以」→ 進入步驟 3
- 如果有調整需求 → 修改後再確認

### 步驟 3: 識別下一步行動

```
很好！那現在最快能開始的是哪一步？

我會幫你標記為「下一步行動」，之後可以直接從這裡開始。
```

### 步驟 4: 完成總結與創建任務卡

```
✅ 幫你整理完成了！

我已經建立了你的第一張「長線任務卡」：

📋 專案：{project_title}
目標：{project_goal}

關鍵步驟：
1. ✓ {step1}
2. → {step2} （下一步）
3. {step3}
4. {step4}

這張任務卡會持續追蹤你的進度，之後我也會從你的工作記錄中自動更新狀態。

---

💡 你的心智空間任務進度：2/3 完成
還差最後一個任務「本週工作節奏」就能完全啟動！
```

## 輸出格式（機器可讀）

對話結束後，輸出 JSON 格式供系統處理：

```json
{
  "onboarding_task": "task2",
  "project_data": {
    "title": "專案標題",
    "description": "專案描述",
    "goal": "期望達到的狀態",
    "steps": [
      {
        "order": 1,
        "title": "步驟 1",
        "description": "具體要做什麼",
        "status": "pending"
      },
      {
        "order": 2,
        "title": "步驟 2",
        "description": "具體要做什麼",
        "status": "next",
        "is_next_action": true
      }
    ],
    "next_action": "步驟 2",
    "estimated_duration": "2-3 週"
  },
  "extracted_insights": {
    "user_working_style": "偏好快速行動 / 喜歡先有框架",
    "potential_blockers": ["時間不夠", "不確定技術方案"],
    "confidence_level": "中等信心"
  }
}
```

## 與心智空間的銜接

1. **自動創建意圖卡**
   - 使用 `project_data` 創建一張 `IntentCard`
   - 設定為 `status: active`, `priority: high`
   - 標記為 onboarding 任務來源

2. **更新冷啟動狀態**
   - 調用 `/api/v1/mindscape/onboarding/complete-task2`
   - 傳入 `execution_id` 和創建的 `intent_id`

3. **提取種子**
   - 從 `extracted_insights` 提取工作風格種子
   - 寫入 `mindscape_seed_log`

## 語氣與風格

- ✅ 輕鬆、口語化（「搞定」而不是「完成」）
- ✅ 主動建議，不要讓用戶填空題
- ✅ 快速完成（3-5 分鐘），不要問太多細節
- ✅ 明確告知進度（2/3 完成）

## 成功標準

- 用戶明確知道這個專案的 3-4 個關鍵步驟
- 用戶知道下一步要做什麼
- 自動創建了第一張長線任務卡
- 冷啟動進度更新為 2/3
