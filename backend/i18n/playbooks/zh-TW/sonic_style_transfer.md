---
playbook_code: sonic_style_transfer
version: 1.0.0
locale: zh-TW
name: "Style Transfer & Coordinate Proximity"
description: "Steer-to-Coordinate style transfer"
kind: user_workflow
capability_code: sonic_space
---

# Style Transfer & Coordinate Proximity

Steer-to-Coordinate style transfer

## 概述

風格轉移 playbook 將一個音訊的風格特性應用到另一個音訊，類似於圖像的神經風格轉移。它啟用創意聲音變形，同時保留內容結構。

**主要功能：**
- 從參考音訊轉移風格
- 保留內容結構
- 應用風格特性
- 建立風格化變化

**目的：**
此 playbook 讓使用者能夠將一個音訊的風格應用到另一個音訊，建立風格化變化，同時保持原始內容結構。它對於創意聲音設計和實驗很有用。

**相關 Playbooks：**
- `sonic_fingerprint_extract` - 提取風格特性
- `sonic_dsp_transform` - 應用風格變形
- `sonic_variation` - 生成風格變化

詳細規格請參考：`playbooks/specs/sonic_style_transfer.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Load Source

Load source audio

- **Action**: `load_source`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Load Target Style

Load target style reference

- **Action**: `load_target_style`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 3: Apply Style Transfer

Apply Steer-to-Coordinate style transfer

- **Action**: `apply_style_transfer`
- **Tool**: `sonic_space.sonic_axes_steer`
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

1. **創意聲音設計**
   - 從參考音訊應用風格
   - 建立風格化變化
   - 實驗聲音特性

2. **品牌適應**
   - 將品牌風格應用到內容
   - 維護品牌音訊識別
   - 建立品牌一致變化

3. **風格實驗**
   - 探索不同的風格應用
   - 建立獨特的聲音組合
   - 生成創意變化

## 使用範例

### 範例 1：轉移風格

```json
{
  "content_audio_id": "audio_123",
  "style_audio_id": "audio_456",
  "style_strength": 0.7
}
```

**預期輸出：**
- 已應用風格的風格化音訊
- 內容結構保留
- 風格特性已轉移

## 技術細節

**風格轉移：**
- 從參考音訊提取風格
- 應用到內容音訊
- 保留內容結構
- 轉移風格特性

**工具依賴：**
- 風格轉移演算法
- 音訊處理工具

## 相關 Playbooks

- **sonic_fingerprint_extract** - 提取風格特性
- **sonic_dsp_transform** - 應用風格變形
- **sonic_variation** - 生成風格變化

## 參考資料

- **規格文件**: `playbooks/specs/sonic_style_transfer.json`
