---
playbook_code: sonic_inpainting
version: 1.0.0
locale: zh-TW
name: "Local Editing"
description: "Edit only a segment, frequency band, or element"
kind: user_workflow
capability_code: sonic_space
---

# Local Editing

Edit only a segment, frequency band, or element

## 概述

局部編輯（Inpainting）playbook 能夠精確編輯音訊中的特定段、頻段或元素，而不影響音訊的其餘部分。它類似於圖像修復，但用於音訊。

**主要功能：**
- 編輯特定音訊區域
- 針對頻段
- 編輯個別元素
- 保留周圍音訊

**目的：**
此 playbook 讓使用者能夠對音訊進行精確編輯，而不影響整個檔案。它對於移除不需要的聲音、增強特定元素或進行針對性改善很有用。

**相關 Playbooks：**
- `sonic_dsp_transform` - 應用變形
- `sonic_segment_extract` - 提取段以供編輯
- `sonic_variation` - 生成變化

詳細規格請參考：`playbooks/specs/sonic_inpainting.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Identify Region

Identify segment/frequency band/element to edit

- **Action**: `identify_region`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Apply Inpainting

Apply local editing

- **Action**: `apply_inpainting`
- **Tool**: `sonic_space.sonic_dsp_transform`
  - ✅ Format: `capability.tool_name`

## 安全檢查

No guardrails defined.

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **噪音移除**
   - 從特定區域移除不需要的聲音
   - 清理音訊段
   - 改善音訊品質

2. **元素增強**
   - 增強特定元素（樂器、人聲）
   - 針對頻段
   - 進行精確改善

3. **選擇性編輯**
   - 僅編輯受影響的區域
   - 保留其餘音訊
   - 維護音訊完整性

## 使用範例

### 範例 1：移除噪音

```json
{
  "audio_asset_id": "asset_123",
  "region": {"start": 10.0, "end": 15.0},
  "edit_type": "noise_removal"
}
```

**預期輸出：**
- 已編輯的音訊，噪音已移除
- 周圍音訊保留
- 品質維持

## 技術細節

**修復流程：**
- 識別目標區域或頻段
- 應用編輯操作
- 保留周圍音訊
- 維護音訊品質

**編輯類型：**
- 噪音移除
- 元素增強
- 頻段編輯
- 選擇性處理

**工具依賴：**
- 音訊編輯和修復工具

## 相關 Playbooks

- **sonic_dsp_transform** - 應用變形
- **sonic_segment_extract** - 提取段以供編輯
- **sonic_variation** - 生成變化

## 參考資料

- **規格文件**: `playbooks/specs/sonic_inpainting.json`
