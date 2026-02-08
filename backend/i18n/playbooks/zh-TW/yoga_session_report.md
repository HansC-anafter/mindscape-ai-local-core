---
playbook_code: yoga_session_report
version: 1.0.0
locale: zh-TW
name: "成果報告與練習回圈"
description: "總結本次練習，追蹤進步，規劃下一次"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: 成果報告與練習回圈

**Playbook Code**: `yoga_session_report`
**版本**: 1.0.0
**用途**: 總結本次練習，追蹤進步，規劃下一次

---

## 輸入資料

```json
{
  "session_id": "session_20251224_001",
  "user_id": "user_123",
  "segments": [
    {
      "segment_id": "seg_001",
      "asana_id": "downward_dog",
      "start_time": 5.2,
      "end_time": 20.8
    }
  ],
  "metrics": [
    {
      "segment_id": "seg_001",
      "angles": {...},
      "symmetry": {...},
      "stability": {...},
      "events": [...]
    }
  ],
  "safety_labels": ["yellow"],
  "events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone"
    }
  ],
  "asanas_practiced": ["downward_dog"],
  "user_feedback": null,
  "user_goal": null,
  "historical_sessions": null
}
```

---

## 處理步驟

### Step 1: 生成本次摘要

計算本次練習的摘要：
- **total_duration**: 總練習時長（秒）
- **segments_analyzed**: 分析的段落數
- **overall_safety**: 整體安全等級（green/yellow/red）
- **key_improvements**: 關鍵改進點（最多 5 個）
- **strengths**: 優點（最多 5 個）

### Step 2: 提取 3 個重點 + 1 個不要做的

從事件和指標中提取：
- **three_key_points**: 3 個最重要的改進點或優點
- **one_avoid_point**: 1 個最需要避免的動作（通常是紅區事件）

### Step 3: 規劃下一次練習

根據當前表現規劃下一次：
- 如果有黃/紅區事件 → 重複相同動作，專注改進點
- 如果全部綠區 → 可以深化練習或進階
- 總是包含休息式（child_pose）

### Step 4: 進步追蹤

與歷史記錄比較：
- **stability_trend**: 穩定度趨勢（improving/stable/degrading）
- **symmetry_trend**: 對稱性趨勢
- **notes**: 進步筆記

---

## 輸出資料

```json
{
  "session_id": "session_20251224_001",
  "user_id": "user_123",
  "date": "2025-12-24T10:30:00Z",
  "asanas_practiced": ["downward_dog"],
  "summary": {
    "total_duration": 30,
    "segments_analyzed": 1,
    "overall_safety": "yellow",
    "key_improvements": [
      "膝蓋對位需注意"
    ],
    "strengths": [
      "肩膀穩定性良好",
      "呼吸節奏平穩"
    ]
  },
  "three_key_points": [
    "注意右膝蓋微彎，避免過度伸直",
    "保持肩膀穩定，這部分做得很好",
    "下次可以嘗試微調髖部高度"
  ],
  "one_avoid_point": "避免膝蓋鎖死承受壓力",
  "next_session_plan": {
    "recommended_asanas": ["downward_dog", "child_pose"],
    "focus_areas": ["膝蓋對位", "髖部穩定"],
    "estimated_duration": 20
  },
  "progress_tracking": {
    "stability_trend": "improving",
    "symmetry_trend": "stable",
    "notes": "膝蓋對位為新的注意點"
  },
  "user_feedback": null
}
```

### 決策邏輯

- 根據 overall_safety 決定下一次練習計劃
- 如果有改進點 → 重複相同動作
- 如果全部綠區 → 可以進階或深化
- 總是包含休息式

---

## 工具依賴

- `yogacoach.session_report` - 成果報告生成工具

---

## 相關文檔

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) 第 7 節









