---
playbook_code: sonic_variation
version: 1.0.0
locale: zh-TW
name: "Reference Audio Variation Generation"
description: "Preserve fingerprint but generate new segments"
kind: user_workflow
capability_code: sonic_space
---

# Reference Audio Variation Generation

Preserve fingerprint but generate new segments

## 概述

參考音訊變化生成 playbook 在保留參考音訊的聲音指紋的同時生成新的音訊段。它建立保留核心特性但提供新創意可能性的變化。

**主要功能：**
- 從參考保留聲音指紋
- 生成帶變化的新段
- 維護核心音訊特性
- 從單一參考建立多樣變化

**目的：**
此 playbook 讓使用者能夠建立參考聲音的多個變化，同時保持其基本特性。它對於建立具有一致特性但多樣選項的聲音庫很有用。

**相關 Playbooks：**
- `sonic_fingerprint_extract` - 從參考提取指紋
- `sonic_dsp_transform` - 為變化應用變形
- `sonic_prospecting_lite` - 通過探索生成變化

詳細規格請參考：`playbooks/specs/sonic_variation.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Load Reference

Load reference audio

- **Action**: `load_reference`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Extract Fingerprint

Extract and preserve fingerprint

- **Action**: `extract_fingerprint`
- **Tool**: `sonic_space.sonic_fingerprint_extractor`
  - ✅ Format: `capability.tool_name`

### Step 3: Generate Variation

Generate new segments preserving fingerprint

- **Action**: `generate_variation`
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

1. **聲音庫擴展**
   - 從參考聲音建立變化
   - 在變化中維護一致特性
   - 建立多樣聲音集合

2. **品牌一致性**
   - 生成維護品牌音訊指紋的變化
   - 建立品牌一致的聲音庫
   - 在變化中保留品牌識別

3. **創意探索**
   - 在保留核心特性的同時探索變化
   - 生成創意替代方案
   - 維護參考品質

## 使用範例

### 範例 1：生成變化

```json
{
  "reference_audio_id": "audio_123",
  "variation_count": 5,
  "preserve_fingerprint": true
}
```

**預期輸出：**
- 多個變化段
- 所有變化都保留參考指紋
- 多樣但一致的特性

## 技術細節

**變化生成：**
- 提取並保留參考指紋
- 應用受控變形
- 維護核心特性
- 生成多樣變化

**工具依賴：**
- `sonic_audio_analyzer` - 載入參考音訊
- `sonic_fingerprint_extractor` - 提取並保留指紋
- `sonic_dsp_transform` - 生成變化

## 相關 Playbooks

- **sonic_fingerprint_extract** - 從參考提取指紋
- **sonic_dsp_transform** - 為變化應用變形
- **sonic_prospecting_lite** - 通過探索生成變化

## 參考資料

- **規格文件**: `playbooks/specs/sonic_variation.json`
