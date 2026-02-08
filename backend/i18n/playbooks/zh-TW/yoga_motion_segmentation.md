---
playbook_code: yoga_motion_segmentation
version: 1.0.0
locale: zh-TW
name: "動作辨識與片段切分"
description: "將影片切分為已授權動作庫可處理的段落，只在老師動作庫範圍內進行辨識"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: 動作辨識與片段切分

**Playbook Code**: `yoga_motion_segmentation`
**版本**: 1.0.0
**用途**: 將影片切分為已授權動作庫可處理的段落，只在老師動作庫範圍內進行辨識

---

## 輸入資料

```json
{
  "keypoints": [
    {
      "frame_id": 0,
      "timestamp": 0.0,
      "keypoints": {
        "nose": {"x": 320, "y": 180, "confidence": 0.95},
        "left_shoulder": {"x": 280, "y": 220, "confidence": 0.92}
      }
    }
  ],
  "teacher_asana_library": [
    "downward_dog",
    "warrior_ii",
    "triangle_pose",
    "bridge_pose",
    "cat_cow"
  ],
  "time_features": []
}
```

---

## 處理步驟

### Step 1: 動作分類（限定動作庫）

使用滑動視窗方式掃描 keypoints：
- 只在 `teacher_asana_library` 範圍內辨識
- 計算與每個 asana 的相似度
- 只接受 confidence > 0.7 的分類結果
- 不在動作庫範圍內的段落標記為 `unrecognized`

### Step 2: 時序切分（起勢/進入/停留/退出）

對每個識別出的 asana 段落：
- 向前向後延伸，找出完整段落
- 檢測 entry（進入）、hold（停留）、exit（退出）階段
- 使用啟發式方法：前 20% = entry，中間 60% = hold，後 20% = exit

### Step 3: 信心分數計算

計算整體信心分數：
- 動作分類信心（50%）
- 關節點偵測品質（30%）
- 階段偵測信心（20%）

### Step 4: 過濾低信心段落

只保留：
- confidence > 0.7 的段落
- duration >= 3 秒的段落

---

## 輸出資料

```json
{
  "segments": [
    {
      "segment_id": "seg_0005",
      "asana_id": "downward_dog",
      "start_time": 5.2,
      "end_time": 20.8,
      "confidence": 0.87,
      "phases": {
        "entry": {"start": 5.2, "end": 8.1},
        "hold": {"start": 8.1, "end": 18.5},
        "exit": {"start": 18.5, "end": 20.8}
      }
    }
  ],
  "unrecognized_segments": [
    {
      "start_time": 25.0,
      "end_time": 30.0,
      "reason": "not_in_library"
    }
  ]
}
```

### 決策邏輯

- 如果有 `segments` 且 confidence > 0.7 → 繼續 Playbook 03
- 如果只有 `unrecognized_segments` → 回傳「動作不在動作庫範圍內」
- 如果沒有 segments → 回傳「無法識別動作」

---

## 工具依賴

- `yogacoach.motion_segmenter` - 動作切分工具
- `yogacoach.rubric_loader` - 載入 asana rubric（用於相似度計算）

---

## 相關文檔

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) 第 2 節









