---
playbook_code: sonic_quick_calibration
version: 1.0.0
locale: zh-TW
name: "Perceptual Axes Quick Calibration"
description: "Calibrate 3 core perceptual axes (warmth/brightness/spatiality) with small annotation set"
kind: user_workflow
capability_code: sonic_space
---

# Perceptual Axes Quick Calibration

Calibrate 3 core perceptual axes (warmth/brightness/spatiality) with small annotation set

## 概述

感知軸快速校準 playbook 使用少量註釋集校準三個核心感知軸（溫暖、亮度、空間感）。這使得在潛在空間中能夠穩定導航，並實現精確的基於維度的導航。

**主要功能：**
- 使用最少註釋（每個軸 30 對）校準 3 個核心軸
- 成對比較註釋收集
- 註釋者間一致性驗證
- 從註釋計算方向向量
- 導航一致性驗證

**目的：**
此 playbook 建立啟用基於維度的聲音導航的感知軸。沒有校準，維度導航不可靠，導航結果不一致。

**相關 Playbooks：**
- `sonic_embedding_build` - 在校準前建立 embeddings
- `sonic_navigation` - 使用校準的軸進行基於維度的搜尋
- `sonic_prospecting_lite` - 使用校準的軸進行聲音生成

詳細規格請參考：`playbooks/specs/sonic_quick_calibration.json`

## 輸入參數

### 必填輸入

- **target_axes** (`array[string]`)
  - Target axes to calibrate
  - Default: `['warmth', 'brightness', 'spatiality']`

### 選填輸入

- **pairs_per_axis** (`integer`)
  - Minimum number of annotation pairs per axis
  - Default: `30`

- **annotators** (`integer`)
  - Number of annotators for cross-validation
  - Default: `2`

- **agreement_threshold** (`float`)
  - Inter-annotator agreement threshold
  - Default: `0.7`

- **embedding_model** (`string`)
  - Embedding model to use for vector calculation
  - Default: `clap`

## 輸出結果

**Artifacts:**

- `perceptual_axes_model`
  - Schema defined in spec file

## 執行步驟

### Step 1: Load Candidate Segments

Load audio segments for pairwise comparison

- **Action**: `load_segments`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Generate Pairwise Comparisons

Generate audio pairs with large differences for each axis

- **Action**: `generate_pairs`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Collect Annotations

Collect pairwise comparison annotations from annotators

- **Action**: `collect_annotations`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Calculate Inter-Annotator Agreement

Calculate agreement between annotators

- **Action**: `calculate_agreement`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: agreement_score

### Step 5: Compute Axis Direction Vectors

Calculate direction vectors from annotations and embeddings

- **Action**: `compute_directions`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Validate Calibration

Validate steer consistency along calibrated axes

- **Action**: `validate_calibration`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 7: Save Calibration Model

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **insufficient_annotations**
  - Rule: Must have at least pairs_per_axis annotations per axis
  - Action: `require_more_annotations`

- **low_agreement**
  - Rule: Inter-annotator agreement below threshold
  - Action: `require_review_and_reannotation`

- **invalid_direction**
  - Rule: Direction vector must be non-zero and normalized
  - Action: `recalculate_or_fail`

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **初始系統校準**
   - 在設定新的 Sonic Space 實例時校準軸
   - 建立基準感知維度
   - 啟用基於維度的導航

2. **軸精煉**
   - 使用更多註釋重新校準軸
   - 改善導航一致性
   - 針對特定使用案例調整

3. **自訂軸校準**
   - 校準超出核心 3 個的自訂軸
   - 領域特定維度
   - 專業化導航需求

## 使用範例

### 範例 1：標準 3 軸校準

```json
{
  "target_axes": ["warmth", "brightness", "spatiality"],
  "pairs_per_axis": 30,
  "annotators": 2,
  "agreement_threshold": 0.7,
  "embedding_model": "clap"
}
```

**預期輸出：**
- `perceptual_axes_model` artifact，包含：
  - 每個軸的方向向量
  - 校準統計
  - 導航一致性分數（目標 > 80%）

## 技術細節

**校準流程：**
1. 載入具有大差異的候選段
2. 為每個軸產生成對比較
3. 從多個註釋者收集註釋
4. 計算註釋者間一致性
5. 從註釋和 embeddings 計算方向向量
6. 驗證校準（導航一致性 > 80%）
7. 儲存校準模型

**核心軸：**
- **溫暖**：溫暖/冷調感知軸
- **亮度**：明亮/暗調感知軸
- **空間感**：寬敞/親密感知軸

**註釋要求：**
- 每個軸至少 30 對
- 多個註釋者進行交叉驗證
- 一致性閾值：0.7（70% 一致性）
- 配對間差異大，以清楚定義軸

**方向向量計算：**
- 使用註釋配對之間的 embedding 差異
- 計算 embedding 空間中的主方向
- 標準化為單位向量
- 驗證非零且已標準化

**導航一致性：**
- 通過沿軸導航測試校準
- 測量感知變化的 consistency
- 目標：> 80% 一致性
- 驗證校準品質

**工具依賴：**
- `sonic_audio_analyzer` - 載入段
- `embedding_tool` - 產生用於計算的 embeddings

**服務依賴：**
- `embedding_service` - Embedding 生成
- `calibration_service` - 校準計算

**效能：**
- 預估時間：完整校準約 3600 秒（1 小時）
- 註釋收集是瓶頸
- 支援配對批次處理

**責任分配：**
- AI Auto：40%（自動配對生成和計算）
- AI Propose：30%（註釋建議）
- Human Only：30%（註釋收集和驗證）

## 相關 Playbooks

- **sonic_embedding_build** - 在校準前建立 embeddings
- **sonic_navigation** - 使用校準的軸進行基於維度的搜尋
- **sonic_prospecting_lite** - 使用校準的軸進行聲音生成
- **sonic_perceptual_axes** - 更多軸的完整校準

## 參考資料

- **規格文件**: `playbooks/specs/sonic_quick_calibration.json`
- **API 端點**: `POST /api/v1/sonic-space/perceptual/calibrate`
