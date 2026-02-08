---
playbook_code: yoga_quality_check
version: 1.0.0
locale: zh-TW
name: "拍攝品質與隱私檢核"
description: "在進入分析前，檢查影片品質是否可分析，並完成隱私承諾閉環"
capability_code: yogacoach
tags:
  - yoga
---

# Playbook: 拍攝品質與隱私檢核

**Playbook Code**: `yoga_quality_check`
**版本**: 1.0.0
**用途**: 在進入分析前，檢查影片品質是否可分析，並完成隱私承諾閉環

---

## 輸入資料

```json
{
  "video_metadata": {
    "duration": 30.5,
    "resolution": "640x480",
    "fps": 15
  },
  "frames_sample": [
    {
      "frame_id": 0,
      "timestamp": 0.0,
      "keypoints": {
        "nose": {"x": 320, "y": 180, "confidence": 0.95},
        "left_shoulder": {"x": 280, "y": 220, "confidence": 0.92}
      }
    }
  ],
  "user_consent": {
    "privacy_policy_accepted": true,
    "data_retention_days": 7
  },
  "user_pain_report": {
    "has_pain": false,
    "pain_location": null,
    "pain_level": null
  }
}
```

---

## 處理步驟

### Step 1: 影片品質檢查

檢查項目：
- 影片時長（10-60 秒）
- 解析度（建議 640x480 以上）
- FPS（建議 15fps 以上）

### Step 2: Keypoints 品質檢核

使用 `KeypointsQualityChecker` 檢查：
- 幀數（至少 150 幀，約 10 秒 @ 15fps）
- 關鍵關節點偵測率（至少 70%）
- 平均置信度（至少 0.6）
- 異常跳動檢測（可能表示偵測失敗）

### Step 3: 隱私承諾回執生成

生成隱私回執，包含：
- 時間戳
- 使用者同意版本
- 儲存的資料類型
- 不儲存的資料類型
- 保留天數
- 刪除 token（用於一鍵刪除）
- 過期時間

### Step 4: 使用者疼痛回報檢查

如果使用者回報疼痛：
- 記錄疼痛資訊
- 後續 Playbook 會根據此資訊調整建議

---

## 輸出資料

```json
{
  "quality_score": 85,
  "confidence_gate": "pass",
  "warnings": [],
  "privacy_receipt": {
    "timestamp": "2025-12-24T10:30:00Z",
    "consent_version": "1.0",
    "data_stored": [
      "keypoints (joint sequence)",
      "metrics (angles, symmetry, stability)",
      "events (error event timestamps)"
    ],
    "data_not_stored": [
      "original video file"
    ],
    "retention_days": 7,
    "deletion_token": "del_abc123xyz",
    "expires_at": "2025-12-31T10:30:00Z"
  }
}
```

### 決策邏輯

- `pass`: 繼續 Playbook 02（動作切分）
- `reject`: 終止流程，回傳重拍指引
- `re_shoot`: 提供具體重拍建議

---

## 工具依賴

- `yogacoach.quality_checker` - 品質檢查工具

---

## 相關文檔

- [YOGACOACH_PLAYBOOK_SPECS.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/YOGACOACH_PLAYBOOK_SPECS.md) 第 1 節
- [ARCHITECTURE_COMPLIANCE_FIX.md](../../../../mindscape-ai-local-core/docs-internal/implementation/yogacoach-capability-2025-12-24/ARCHITECTURE_COMPLIANCE_FIX.md) 第 2.1-2.2 節









