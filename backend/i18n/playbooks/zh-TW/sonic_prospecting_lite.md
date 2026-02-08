---
playbook_code: sonic_prospecting_lite
version: 1.0.0
locale: zh-TW
name: "Latent Space Prospecting (Lite)"
description: "DSP interpolation/extrapolation to generate new sound candidates (P0 version)"
kind: user_workflow
capability_code: sonic_space
---

# Latent Space Prospecting (Lite)

DSP interpolation/extrapolation to generate new sound candidates (P0 version)

## 概述

潛在空間探索（Lite）playbook 通過在書籤之間插值或沿感知軸外推來產生新的聲音候選項。這是使用 DSP 變形而非 AI 生成的 P0 版本聲音生成。

**主要功能：**
- 兩個書籤之間的插值
- 沿感知軸的外推
- 基於 DSP 的變形（EQ、混響、時間拉伸等）
- 生成候選項的品質驗證
- 多種探索策略

**目的：**
此 playbook 讓使用者能夠探索潛在空間並產生新的聲音變化，無需 AI 生成模型。這是一種輕量級的聲音生成方法，可與現有資產配合使用。

**相關 Playbooks：**
- `sonic_bookmark` - 為插值/外推建立書籤
- `sonic_quick_calibration` - 為外推校準軸
- `sonic_dsp_transform` - 應用 DSP 變形
- `sonic_navigation` - 尋找用作書籤的聲音

詳細規格請參考：`playbooks/specs/sonic_prospecting_lite.json`

## 輸入參數

### 必填輸入

- **method** (`enum`)
  - Prospecting method: interpolate between bookmarks or extrapolate along axis
  - Options: interpolate, extrapolate

### 選填輸入

- **bookmark_a_id** (`string`)
  - First bookmark ID (for interpolation)

- **bookmark_b_id** (`string`)
  - Second bookmark ID (for interpolation)

- **bookmark_id** (`string`)
  - Bookmark ID (for extrapolation)

- **axis** (`string`)
  - Axis name for extrapolation (warmth/brightness/spatiality)

- **direction** (`integer`)
  - Direction for extrapolation (+1 or -1)
  - Default: `1`

- **magnitude** (`float`)
  - Extrapolation magnitude (0-1)
  - Default: `0.3`

- **interpolation_steps** (`integer`)
  - Number of interpolation steps (for interpolation method)
  - Default: `3`

## 輸出結果

**Artifacts:**

- `prospecting_candidates`
  - Schema defined in spec file

## 執行步驟

### Step 1: Load Bookmarks

Load bookmark(s) and representative segments

- **Action**: `load_bookmarks`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Load Audio Files

Load audio files for bookmarks

- **Action**: `load_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Generate Candidates

Generate new sound candidates using DSP

- **Action**: `generate_candidates`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Apply DSP Transformations

Apply EQ, reverb, saturation, etc. based on method and parameters

- **Action**: `apply_dsp`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Validate Candidates

Validate generated candidates (duration, quality, etc.)

- **Action**: `validate`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Create Candidate Set

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **bookmark_required**
  - Rule: At least one bookmark must be provided
  - Action: `reject_with_message`

- **interpolation_bookmarks**
  - Rule: Interpolation requires exactly 2 bookmarks
  - Action: `reject_with_message`

- **extrapolation_axis**
  - Rule: Extrapolation requires valid axis name
  - Action: `reject_with_message`

- **magnitude_range**
  - Rule: Extrapolation magnitude must be between 0 and 1
  - Action: `reject_with_message`

- **quality_check**
  - Rule: Generated candidates must pass minimal quality checks
  - Action: `reject_with_qa_report`

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **聲音間插值**
   - 在兩個書籤之間產生中間聲音
   - 建立平滑過渡
   - 探索潛在空間中的中間地帶

2. **基於軸的外推**
   - 通過沿感知軸移動產生聲音
   - 範例：使聲音更溫暖、更明亮或更寬敞
   - 探索維度極端

3. **變化生成**
   - 建立現有聲音的變化
   - 保留核心特性
   - 產生多個候選項以供選擇

## 使用範例

### 範例 1：插值

```json
{
  "method": "interpolate",
  "bookmark_a_id": "bookmark_123",
  "bookmark_b_id": "bookmark_456",
  "interpolation_steps": 5
}
```

**預期輸出：**
- `prospecting_candidates` artifact，包含 5 個中間聲音
- 兩個書籤之間的平滑過渡
- 所有候選項通過品質檢查

### 範例 2：外推

```json
{
  "method": "extrapolate",
  "bookmark_id": "bookmark_789",
  "axis": "warmth",
  "direction": 1,
  "magnitude": 0.5
}
```

**預期輸出：**
- `prospecting_candidates` artifact，包含更溫暖的變化
- 通過沿溫暖軸移動產生
- 品質驗證

## 技術細節

**探索方法：**
- `interpolate`：在兩個書籤之間產生聲音
- `extrapolate`：從書籤沿軸移動產生聲音

**DSP 變形：**
- **EQ**：頻率塑形
- **混響**：空間效果
- **時間拉伸**：節奏變化
- **音高偏移**：音高修改
- **飽和度**：諧波增強
- **顆粒**：顆粒合成效果

**插值流程：**
1. 載入兩個書籤和代表性段
2. 計算潛在空間中的插值路徑
3. 產生中間位置
4. 應用 DSP 變形以建立聲音
5. 驗證品質

**外推流程：**
1. 載入書籤和代表性段
2. 計算沿指定軸的方向
3. 按幅度在方向移動
4. 應用 DSP 變形
5. 驗證品質

**品質驗證：**
- 時長檢查
- 響度驗證
- 格式驗證
- 偽影檢測

**工具依賴：**
- `dsp_engine` - DSP 變形
- `sonic_audio_analyzer` - 音訊分析

**服務依賴：**
- `dsp_processing` - DSP 處理流程
- `prospecting_lite` - 探索邏輯

**效能：**
- 預估時間：每個候選集約 60 秒
- 異步處理
- 支援批次生成

**責任分配：**
- AI Auto：60%（自動生成）
- AI Propose：30%（參數建議）
- Human Only：10%（最終選擇）

## 相關 Playbooks

- **sonic_bookmark** - 為插值/外推建立書籤
- **sonic_quick_calibration** - 為外推校準軸
- **sonic_dsp_transform** - 應用 DSP 變形
- **sonic_navigation** - 尋找用作書籤的聲音
- **sonic_latent_prospecting** - 進階探索（P1）

## 參考資料

- **規格文件**: `playbooks/specs/sonic_prospecting_lite.json`
- **API 端點**: `POST /api/v1/sonic-space/prospecting/generate`
