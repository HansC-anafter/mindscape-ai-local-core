---
playbook_code: yoga_safety_engine
version: 1.0.0
locale: zh-TW
name: "安全策略引擎"
description: "決策層，決定可以給哪些回饋、禁止哪些危險建議。這是產品的護城河。"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: 安全策略引擎

**Playbook Code**: `yoga_safety_engine`
**版本**: 1.0.0
**用途**: 決策層，決定可以給哪些回饋、禁止哪些危險建議。這是產品的護城河。

---

## 輸入資料

```json
{
  "events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5
    }
  ],
  "metrics": {
    "angles": {...},
    "symmetry": {...},
    "stability": {...}
  },
  "video_quality_confidence": 0.85,
  "user_pain_report": {
    "has_pain": false,
    "pain_location": null,
    "pain_level": null
  }
}
```

---

## 處理步驟

### Step 1: 評估可信度門檻

檢查影片品質和事件可信度：
- 如果 `video_quality_confidence < 0.5` → `low` 可信度
- 如果 `video_quality_confidence < 0.7` → `medium` 可信度
- 如果超過 50% 的事件可信度 < 0.7 → `medium` 可信度
- 否則 → `high` 可信度

### Step 2: 檢查疼痛回報

如果使用者回報疼痛：
- 停止所有進階建議
- 只提供替代動作
- 標記為 `red` 安全等級

### Step 3: 決策矩陣

根據可信度、疼痛狀態、事件嚴重度決定允許的操作：

**規則 1: 低可信度**
- ❌ 不提供詳細回饋
- ✅ 提供替代動作
- ✅ 顯示老師示範

**規則 2: 疼痛回報**
- ❌ 不提供詳細回饋
- ❌ 不建議進階動作
- ✅ 只提供替代動作

**規則 3: 紅區事件**
- ✅ 提供詳細回饋
- ❌ 不建議進階動作
- ✅ 建議修改動作
- ✅ 提供替代動作
- ✅ 顯示錯誤示範

**規則 4: 黃區事件**
- ✅ 提供詳細回饋
- ❌ 不建議進階動作
- ✅ 建議修改動作
- ✅ 顯示錯誤示範

**規則 5: 全部綠區**
- ✅ 提供詳細回饋
- ✅ 可以建議進階動作
- ✅ 建議修改動作

### Step 4: 優先級排序

將事件按嚴重度排序：
- 紅區事件優先
- 黃區事件次之
- 按數值大小排序

---

## 輸出資料

```json
{
  "allowed_actions": {
    "give_detailed_feedback": true,
    "suggest_progression": false,
    "suggest_modifications": true,
    "suggest_alternatives": true,
    "show_teacher_demo": true,
    "show_error_demo": true,
    "safety_label": "yellow",
    "reason": "Yellow zone events detected: 1"
  },
  "prioritized_events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5
    }
  ],
  "summary": {
    "confidence_level": "high",
    "confidence_reason": "confidence_sufficient",
    "pain_detected": false,
    "total_events": 1,
    "red_events": 0,
    "yellow_events": 1,
    "safety_label": "yellow"
  },
  "confidence_assessment": {
    "level": "high",
    "reason": "confidence_sufficient",
    "video_confidence": 0.85
  },
  "pain_status": {
    "pain_detected": false,
    "action": "continue"
  }
}
```

### 決策邏輯

- 根據 `allowed_actions` 決定後續 Playbook 的行為
- `safety_label` 用於前端顯示（綠/黃/紅標籤）
- `prioritized_events` 用於 Playbook 05（老師示範對位）

---

## 工具依賴

- `yogacoach.safety_engine` - 安全策略決策引擎

---

## 相關文檔

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) 第 4 節
- [ARCHITECTURE_COMPLIANCE_FIX.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/ARCHITECTURE_COMPLIANCE_FIX.md) 第 3 節









