---
playbook_code: sonic_fingerprint_extract
version: 1.0.0
locale: zh-TW
name: "Sonic Fingerprint Extraction"
description: "Extract Sonic Fingerprint (Brand Audio-VI)"
kind: user_workflow
capability_code: sonic_space
---

# Sonic Fingerprint Extraction

Extract Sonic Fingerprint (Brand Audio-VI)

## 概述

聲音指紋提取 playbook 從音訊資產中提取聲音指紋，建立可用於品牌識別、相似度匹配和音視覺識別（Brand Audio-VI）的獨特音訊簽名。

**主要功能：**
- 從音訊中提取獨特聲音指紋
- 建立品牌音訊簽名
- 支援音視覺識別匹配
- 基於指紋的相似度檢測

**目的：**
此 playbook 建立代表音訊資產獨特特性的聲音指紋。這些指紋用於品牌識別、相似度匹配和維護音視覺品牌一致性。

**相關 Playbooks：**
- `sonic_asset_import` - 在提取指紋前匯入資產
- `sonic_navigation` - 使用指紋進行相似度搜尋
- `sonic_logo_gen` - 從指紋生成品牌音訊標誌

詳細規格請參考：`playbooks/specs/sonic_fingerprint_extract.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Load Audio

Load audio for fingerprint extraction

- **Action**: `load_audio`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Extract Fingerprint

Extract Sonic Fingerprint (Brand Audio-VI)

- **Action**: `extract_fingerprint`
- **Tool**: `sonic_space.sonic_fingerprint_extractor`
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

1. **品牌音訊識別**
   - 為品牌音訊識別提取指紋
   - 為品牌建立獨特音訊簽名
   - 維護品牌音訊一致性

2. **相似度匹配**
   - 使用指紋尋找相似聲音
   - 匹配音訊特性
   - 識別音訊重複

3. **音視覺識別**
   - 建立 Brand Audio-VI（視覺識別）
   - 將音訊匹配到視覺品牌元素
   - 維護跨媒體品牌一致性

## 使用範例

### 範例 1：提取品牌指紋

```json
{
  "audio_asset_id": "asset_123",
  "fingerprint_type": "brand_audio_vi"
}
```

**預期輸出：**
- `sonic_fingerprint` artifact，包含：
  - 獨特指紋簽名
  - 品牌音訊特性
  - 連結到來源音訊資產

## 技術細節

**指紋提取：**
- 分析音訊特性（頻譜、時域、感知）
- 建立獨特簽名表示
- 支援多種指紋類型
- 啟用相似度匹配

**工具依賴：**
- `sonic_audio_analyzer` - 載入和分析音訊
- `sonic_fingerprint_extractor` - 提取指紋

## 相關 Playbooks

- **sonic_asset_import** - 在提取指紋前匯入資產
- **sonic_navigation** - 使用指紋進行相似度搜尋
- **sonic_logo_gen** - 從指紋生成品牌音訊標誌

## 參考資料

- **規格文件**: `playbooks/specs/sonic_fingerprint_extract.json`
