---
playbook_code: sonic_segment_extract
version: 1.0.0
locale: zh-TW
name: "Audio Segmentation & Feature Extraction"
description: "Segment audio into searchable chunks and extract features for C02 rerank"
kind: user_workflow
capability_code: sonic_space
---

# Audio Segmentation & Feature Extraction

Segment audio into searchable chunks and extract features for C02 rerank

## 概述

音訊切段與特徵提取 playbook 將標準化的音訊資產處理為可搜尋的段，並提取音訊特徵以供導航流程中的重新排序。這是啟用向量搜尋和基於特徵過濾的關鍵預處理步驟。

**主要功能：**
- 多種切段策略（固定長度、基於起始點、基於靜音、對齊節拍）
- 音訊特徵提取（頻譜質心、通量、低中頻比、RMS、動態範圍、節拍穩定性、混響比）
- 特徵標準化至 0-100 刻度以確保一致的重新排序
- 靜音段檢測和過濾
- 淡入/淡出應用以實現平滑播放

**目的：**
此 playbook 為 embedding 生成和向量搜尋準備音訊資產。段是搜尋和導航的原子單位，特徵用於導航流程中的精確重新排序。

**相關 Playbooks：**
- `sonic_asset_import` - 在切段前匯入資產
- `sonic_embedding_build` - 從段建立 embeddings
- `sonic_navigation` - 使用段特徵進行重新排序

詳細規格請參考：`playbooks/specs/sonic_segment_extract.json`

## 輸入參數

### 必填輸入

- **audio_asset_id** (`string`)
  - Audio asset ID from A01

## 輸出結果

**Artifacts:**

- `segment`
  - Schema defined in spec file

- `segment_index`
  - Schema defined in spec file

## 執行步驟

### Step 1: Load Audio Asset

Load normalized audio from A01

- **Action**: `load_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Resample to Standard Rate

- **Action**: `resample`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Mix to Mono

- **Action**: `mix_channels`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Segment Audio

- **Action**: `segment_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Apply Fade In/Out

- **Action**: `apply_fades`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Detect Silent Segments

- **Action**: `detect_silence`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 7: Extract Audio Features

- **Action**: `extract_features`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 8: Normalize Features to 0-100

Scale features to 0-100 for rerank consistency

- **Action**: `normalize_features`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 9: Create Segment Index

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **min_segments**
  - Rule: Audio must produce at least 1 non-silent segment
  - Action: `reject_with_message`

- **feature_nan_check**
  - Rule: No NaN values in extracted features
  - Action: `retry_or_fail`

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **固定長度切段**
   - 將長格式音訊切段為固定長度的區塊
   - 適用於環境音和背景音樂
   - 一致的段時長以便搜尋

2. **基於起始點的切段**
   - 在音樂起始點切段
   - 保留音樂結構
   - 適用於循環和節奏內容

3. **基於靜音的切段**
   - 在靜音邊界切段
   - 自然斷點
   - 適用於語音和對話

4. **對齊節拍的切段**
   - 對齊節拍網格切段
   - 保留音樂時序
   - 適用於音樂製作

## 使用範例

### 範例 1：標準切段

```json
{
  "audio_asset_id": "asset_123"
}
```

**預期輸出：**
- 每個提取段的 `segment` artifacts
- 包含所有段的 `segment_index` artifact
- 標準化至 0-100 刻度的特徵
- 過濾掉的靜音段

## 技術細節

**切段策略：**
- `fixed_length`：固定時長的段（例如 5 秒）
- `onset_based`：在起始點檢測點切段
- `silence_based`：在靜音邊界切段
- `beat_aligned`：對齊節拍網格切段

**提取的特徵：**
- `spectral_centroid`：亮度指標
- `spectral_flux`：音色變化率
- `low_mid_ratio`：頻率平衡
- `rms`：能量等級
- `dynamic_range`：響度變化
- `tempo_stability`：節奏一致性
- `reverb_ratio`：空間特性

**特徵標準化：**
- 所有特徵縮放至 0-100 範圍
- 確保不同音訊類型的一致重新排序
- 啟用基於維度的過濾

**處理流程：**
1. 載入標準化音訊資產
2. 重新取樣至標準速率（如需要）
3. 混音為單聲道（用於分析）
4. 使用選定的策略切段音訊
5. 對段應用淡入/淡出
6. 檢測並過濾靜音段
7. 為每個段提取音訊特徵
8. 將特徵標準化至 0-100 刻度
9. 建立段索引

**工具依賴：**
- `sonic_audio_analyzer` - 音訊分析和特徵提取

**服務依賴：**
- `librosa` - 音訊處理和分析
- `numpy` - 數值計算

**效能：**
- 預估時間：每分鐘音訊約 5 秒
- 長檔案的異步處理
- 支援批次處理

**責任分配：**
- AI Auto：95%（完全自動化處理）
- AI Propose：5%（策略選擇建議）
- Human Only：0%（無需人工介入）

## 相關 Playbooks

- **sonic_asset_import** - 在切段前匯入資產
- **sonic_embedding_build** - 從段建立 embeddings
- **sonic_navigation** - 使用段特徵進行重新排序
- **sonic_kit_packaging** - 將段打包成 sound kits

## 參考資料

- **規格文件**: `playbooks/specs/sonic_segment_extract.json`
- **API 端點**: `POST /api/v1/sonic-space/segments/extract`
