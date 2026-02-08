---
playbook_code: sonic_qa
version: 1.0.0
locale: zh-TW
name: "Quality Assurance & Consistency QA"
description: "Volume/frequency/compression detection"
kind: user_workflow
capability_code: sonic_space
---

# Quality Assurance & Consistency QA

Volume/frequency/compression detection

## 概述

品質保證與一致性 QA playbook 對音訊資產執行全面的品質檢查，檢測響度、頻率分佈和壓縮一致性的問題。它確保音訊資產在使用前符合品質標準。

**主要功能：**
- 響度等級檢測和驗證
- 頻段分析
- 壓縮一致性檢查
- 品質報告生成

**目的：**
此 playbook 確保所有音訊資產在生產使用前符合品質標準。它檢測常見的音訊問題並提供詳細的品質報告。

**相關 Playbooks：**
- `sonic_asset_import` - 在匯入後執行 QA
- `sonic_segment_extract` - 在提取後 QA 段
- `sonic_kit_packaging` - 在打包前 QA

詳細規格請參考：`playbooks/specs/sonic_qa.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Check Volume

Check volume levels

- **Action**: `check_volume`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Check Frequency

Check frequency bands

- **Action**: `check_frequency`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 3: Check Compression

Check compression consistency

- **Action**: `check_compression`
- **Tool**: `sonic_space.sonic_audio_analyzer`
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

1. **匯入品質檢查**
   - 在匯入後驗證音訊品質
   - 檢測響度、頻率、壓縮問題
   - 生成品質報告

2. **批次品質驗證**
   - 一次檢查多個資產
   - 確保集合的一致性
   - 識別有問題的檔案

3. **打包前 QA**
   - 在打包前驗證資產
   - 確保套件品質標準
   - 為分發生成 QA 報告

## 使用範例

### 範例 1：標準 QA 檢查

```json
{
  "audio_asset_id": "asset_123",
  "checks": ["volume", "frequency", "compression"]
}
```

**預期輸出：**
- QA 報告，包含：
  - 響度等級分析
  - 頻率分佈
  - 壓縮一致性
  - 品質分數和建議

## 技術細節

**品質檢查：**
- **響度**：檢測削波、過度響度、電平一致性
- **頻率**：分析頻率分佈，檢測缺失頻段
- **壓縮**：檢查壓縮一致性，檢測偽影

**工具依賴：**
- `sonic_audio_analyzer` - 音訊分析和品質檢測

## 相關 Playbooks

- **sonic_asset_import** - 在匯入後執行 QA
- **sonic_segment_extract** - 在提取後 QA 段
- **sonic_kit_packaging** - 在打包前 QA

## 參考資料

- **規格文件**: `playbooks/specs/sonic_qa.json`
