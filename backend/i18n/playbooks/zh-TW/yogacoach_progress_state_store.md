---
playbook_code: yogacoach_progress_state_store
version: 1.0.0
locale: zh-TW
name: "進展狀態存儲"
description: "存儲每次 session 的關鍵指標，計算趨勢，生成下次練習計劃"
capability_code: yogacoach
tags:
  - yoga
  - progress
  - tracking
---

# Playbook: 進展狀態存儲

**Playbook Code**: `yogacoach_progress_state_store`
**版本**: 1.0.0
**用途**: 存儲每次 session 的關鍵指標，計算趨勢，生成下次練習計劃

---

## 輸入資料

**注意**：`tenant_id`、`user_id`、`session_id` 等 cloud 專用欄位由 runtime 從 execution envelope 提供，不在 playbook inputs 中。

```json
{
  "session_report": {
    "asanas_practiced": ["downward_dog", "warrior_ii"],
    "key_metrics": {
      "alignment_score": 78,
      "stability_score": 85,
      "symmetry_score": 72
    },
    "safety_labels": ["yellow", "green"],
    "events": []
  },
  "user_feedback": {
    "difficulty_rating": 3,
    "enjoyed": true,
    "wants_deeper": false,
    "wants_new": true
  }
}
```

## 輸出資料

```json
{
  "student_profile": {
    "user_id": "user-123",
    "total_sessions": 12,
    "total_minutes": 180,
    "asanas_mastered": ["mountain", "forward_fold"],
    "asanas_in_progress": ["downward_dog", "warrior_ii"],
    "weak_areas": ["symmetry", "wrist_pressure"]
  },
  "trend_vectors": {
    "alignment_score": {
      "current": 78,
      "previous": 75,
      "trend": "improving",
      "change_percent": 4.0
    }
  },
  "next_plan": {
    "recommended_asanas": ["warrior_ii", "triangle_pose"],
    "focus_areas": ["symmetry", "balance"],
    "estimated_difficulty": 3,
    "rationale": "基於你在戰士二式的進步，建議嘗試三角式以進一步提升平衡和對稱性"
  }
}
```

## 執行步驟

1. **存儲進展快照**
   - 從 `session_report` 提取關鍵指標
   - 存儲到 student_profiles 表

2. **計算趨勢**
   - 比較當前指標與歷史指標
   - 計算改善/退步/穩定趨勢
   - 生成 trend_vectors

3. **更新學員檔案**
   - 更新 total_sessions、total_minutes
   - 更新 asanas_mastered、asanas_in_progress
   - 更新 weak_areas

4. **生成下次練習計劃**
   - 基於歷史數據和趨勢
   - 推薦適合的 asanas
   - 生成 focus_areas 和 rationale

## 能力依賴

- `yogacoach.progress_tracker`: 進展追蹤

**注意**：使用 capability_code 描述需求，而非硬寫死工具路徑。實際工具由 runtime 根據 capability_code 解析。

## 錯誤處理

- Session Report 格式錯誤：返回錯誤，記錄日誌
- 進展存儲失敗：返回錯誤，記錄日誌

