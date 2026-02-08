---
playbook_code: sonic_kit_packaging
version: 1.0.0
locale: zh-TW
name: "Sound Kit Packaging"
description: "Package SFX/Loop/Ambience packs for commercial distribution"
kind: user_workflow
capability_code: sonic_space
---

# Sound Kit Packaging

Package SFX/Loop/Ambience packs for commercial distribution

## 概述

Sound Kit 打包 playbook 是 Sonic Space 系統中實現商業化的最短路徑。它不是製作完整歌曲，而是將策劃的聲音段打包成可分發和銷售的商業 sound kits（SFX、Loops、Ambience）。

**核心概念**：實現商業化的最短路徑：不是製作歌曲，而是製作「sound kits」——內容創作者需要的聲音效果、循環和環境音的策劃集合。

**主要功能：**
- 自動資料夾結構組織
- 檔案命名慣例應用
- 批次音訊標準化
- 預覽檔案生成
- 元數據和授權檔案編譯
- 使用說明 README 生成
- ZIP 封存建立

**目的：**
此 playbook 將個別聲音段轉換為專業、可分發的 sound kits。它確保所有檔案都經過適當組織、標準化、授權和文件化，以供商業分發。

**相關 Playbooks：**
- `sonic_navigation` - 尋找要包含在 kit 中的段
- `sonic_license_governance` - 確保所有段都有有效授權
- `sonic_export_gate` - 分發前的最終合規檢查
- `sonic_segment_extract` - 提取段以供打包

詳細規格請參考：`playbooks/specs/sonic_kit_packaging.json`

## 輸入參數

### 必填輸入

- **kit_name** (`string`)
  - Kit name

- **kit_type** (`enum`)
  - Type of sound kit
  - Options: sfx, loop, ambience, ui_sound, mixed

- **segment_ids** (`array[string]`)
  - List of segment IDs to package

### 選填輸入

- **naming_convention** (`enum`)
  - File naming convention
  - Default: `descriptive`
  - Options: category_number, descriptive, brand_prefix

- **include_variations** (`boolean`)
  - Default: `True`

- **target_format** (`object`)

## 輸出結果

**Artifacts:**

- `sound_kit`
  - Schema defined in spec file

## 執行步驟

### Step 1: Collect Segments

Gather all segments for packaging

- **Action**: `gather_segments`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Verify Licenses

Ensure all segments have valid licenses

- **Action**: `check_all_licenses`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Organize Folder Structure

Create standardized folder structure

- **Action**: `create_folder_structure`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Apply Naming Convention

Rename files according to convention

- **Action**: `rename_files`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Normalize Audio

Normalize loudness and peaks

- **Action**: `batch_normalize`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Generate Preview Files

Create low-quality preview files

- **Action**: `create_previews`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 7: Generate Metadata

Create metadata.json with kit information

- **Action**: `create_metadata_file`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 8: Generate License File

Compile all licenses into LICENSE.md

- **Action**: `compile_licenses`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 9: Generate README

Generate README with usage instructions

- **Action**: `generate_readme`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 10: Package Kit

Create final ZIP archive

- **Action**: `create_archive`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **license_aggregation**
  - Rule: Most restrictive license applies to kit
  - Action: `warn_and_document`

- **quality_check**
  - Rule: All files must pass audio QA
  - Action: `reject_failing_files`

- **naming_conflict**
  - Rule: Detect naming conflicts
  - Action: `auto_rename_with_suffix`

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **SFX 包建立**
   - 將聲音效果打包成主題包
   - 按類別組織（UI 聲音、撞擊、過渡）
   - 為行銷產生預覽檔案

2. **循環包分發**
   - 為音樂製作打包音訊循環
   - 確保一致的節奏和調性
   - 產生混音指南

3. **環境音集合**
   - 為內容創作打包環境聲音
   - 按環境組織（自然、城市、室內）
   - 包含使用說明

4. **混合 Kit 建立**
   - 結合 SFX、循環和環境音
   - 建立全面的聲音庫
   - 產生完整文件

## 使用範例

### 範例 1：SFX 包

```json
{
  "kit_name": "UI_Sound_Effects_Vol1",
  "kit_type": "sfx",
  "segment_ids": ["seg_001", "seg_002", "seg_003", ...],
  "naming_convention": "category_number",
  "include_variations": true
}
```

**預期輸出：**
- `sound_kit` artifact，包含 ZIP 封存
- 資料夾結構：`UI_Sound_Effects_Vol1/audio/ui/`、`previews/` 等
- `sound_tokens.json`，包含所有段元數據
- `LICENSE.md`，包含匯總的授權
- `README.md`，包含使用說明

### 範例 2：循環包

```json
{
  "kit_name": "LoFi_Beats_Collection",
  "kit_type": "loop",
  "segment_ids": ["seg_101", "seg_102", ...],
  "naming_convention": "descriptive",
  "target_format": {
    "sample_rate": 44100,
    "bit_depth": 24,
    "format": "wav"
  }
}
```

**預期輸出：**
- `sound_kit` artifact，包含標準化循環
- `mix_guideline.md`，包含混音說明
- BPM 和調性資訊在元數據中
- 每個循環的預覽檔案

## 技術細節

**Kit 類型：**
- `sfx`：聲音效果（短、單次聲音）
- `loop`：音訊循環（重複模式）
- `ambience`：環境聲音（長格式、大氣）
- `ui_sound`：UI 互動聲音
- `mixed`：多種類型的組合

**命名慣例：**
- `category_number`：`ui_click_001.wav`
- `descriptive`：`warm_ambient_nature.wav`
- `brand_prefix`：`BrandName_UI_Click.wav`

**封包結構：**
```
{kit_name}/
├── README.md
├── LICENSE.md
├── metadata.json
├── sound_tokens.json
├── mix_guideline.md (for loops)
├── previews/
│   └── *.mp3
└── audio/
    ├── {category}/
    │   └── *.{format}
```

**授權匯總：**
- 最嚴格的授權適用於整個 kit
- 所有授權編譯到 LICENSE.md
- 檢查授權相容性

**品質檢查：**
- 所有檔案必須通過音訊 QA
- 一致的響度標準化
- 格式驗證
- 命名衝突解決

**工具依賴：**
- `sonic_kit_packager` - 封包建立和組織
- `sonic_audio_analyzer` - 音訊品質檢查

**責任分配：**
- AI Auto：70%（自動打包和組織）
- AI Propose：20%（命名和結構建議）
- Human Only：10%（最終審核和批准）

## 相關 Playbooks

- **sonic_navigation** - 尋找要包含在 kit 中的段
- **sonic_license_governance** - 確保所有段都有有效授權
- **sonic_export_gate** - 分發前的最終合規檢查
- **sonic_segment_extract** - 提取段以供打包
- **sonic_dsp_transform** - 為 kit 建立變化

## 參考資料

- **規格文件**: `playbooks/specs/sonic_kit_packaging.json`
