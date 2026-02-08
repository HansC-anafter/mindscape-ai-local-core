---
playbook_code: yoga_pose_assessment
version: 1.0.0
locale: zh-TW
name: "姿勢評估與指標計算"
description: "計算角度、對稱、穩定度等指標，並與 rubric 對照找出黃/紅事件"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: 姿勢評估與指標計算

**Playbook Code**: `yoga_pose_assessment`
**版本**: 1.0.0
**用途**: 計算角度、對稱、穩定度等指標，並與 rubric 對照找出黃/紅事件

---

## 輸入資料

```json
{
  "segments": [
    {
      "segment_id": "seg_0005",
      "asana_id": "downward_dog",
      "keypoints": [
        {
          "frame_id": 0,
          "timestamp": 5.2,
          "keypoints": {
            "nose": {"x": 320, "y": 180, "confidence": 0.95},
            "left_shoulder": {"x": 280, "y": 220, "confidence": 0.92}
          }
        }
      ]
    }
  ],
  "rubric": {
    "asana_code": "downward_dog",
    "key_angles": [...],
    "symmetry_checks": [...],
    "stability_indicators": [...]
  }
}
```

---

## 處理步驟

### Step 1: 關節點平滑濾波

使用 Savitzky-Golay 濾波器平滑關節點軌跡：
- 減少偵測雜訊
- 保持動作的平滑性
- 視窗大小：5 幀，多項式階數：2

### Step 2: 計算關節角度

根據 rubric 中的 `key_angles` 定義計算角度：
- 對每個關鍵角度，計算整個段落的平均值、最小值、最大值、變異數
- 使用三點角度計算方法（p1-p2-p3）

### Step 3: 對稱性檢查

根據 rubric 中的 `symmetry_checks` 檢查左右對稱：
- 計算左右關節點的平均位置差異
- 與 `max_diff_degrees` 閾值比較
- 標記是否在閾值內

### Step 4: 穩定度評估

根據 rubric 中的 `stability_indicators` 評估穩定度：
- 計算重心位置變異數（center_of_gravity）
- 計算手掌位置變異數（hand_placement_stability）
- 與 `max_variance` 閾值比較

### Step 5: 事件偵測（黃/紅區）

偵測黃/紅區事件：
- **角度事件**: 檢查角度是否在 yellow_range 或 red_range
- **對稱事件**: 檢查對稱性是否超出閾值
- **穩定度事件**: 檢查穩定度是否不穩定
- **代償事件**: 檢查常見代償動作（簡化版）

---

## 輸出資料

```json
{
  "metrics": [
    {
      "segment_id": "seg_0005",
      "angles": {
        "hip_flexion": {
          "avg": 105.2,
          "min": 98.5,
          "max": 112.3,
          "variance": 8.5
        }
      },
      "symmetry": {
        "shoulder_symmetry": {
          "left_avg": 220.5,
          "right_avg": 221.2,
          "diff": 0.7,
          "within_threshold": true
        }
      },
      "stability": {
        "center_of_gravity": {
          "variance": 3.2,
          "status": "stable"
        }
      },
      "events": [
        {
          "type": "knee_hyperextension_yellow",
          "severity": "yellow",
          "description": "Knee angle in yellow zone",
          "value": 178.5,
          "angle_name": "knee_angle"
        }
      ]
    }
  ],
  "events": [
    {
      "type": "knee_hyperextension_yellow",
      "severity": "yellow",
      "description": "Knee angle in yellow zone",
      "value": 178.5
    }
  ],
  "summary": {
    "total_segments": 1,
    "total_events": 1,
    "red_events": 0,
    "yellow_events": 1
  }
}
```

### 決策邏輯

- 如果有 red_events → 繼續 Playbook 04（安全策略引擎）
- 如果只有 yellow_events → 繼續 Playbook 04（安全策略引擎）
- 如果沒有 events → 繼續 Playbook 05（老師示範對位）

---

## 工具依賴

- `yogacoach.pose_assessment` - 姿勢評估工具
  - `AngleCalculator` - 角度計算
  - `SymmetryChecker` - 對稱性檢查
  - `StabilityAssessor` - 穩定度評估
  - `EventDetector` - 事件偵測

---

## 相關文檔

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) 第 3 節









