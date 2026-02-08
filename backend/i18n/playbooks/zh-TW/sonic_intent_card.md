---
playbook_code: sonic_intent_card
version: 1.0.0
locale: zh-TW
name: "Sonic Intent Card Generation"
description: "Transform natural language requirements into actionable sonic dimensions"
kind: user_workflow
capability_code: sonic_space
---

# Sonic Intent Card Generation

Transform natural language requirements into actionable sonic dimensions

## 概述

Sonic Intent Card 生成 playbook 將自然語言需求轉換為可執行的聲音維度。它將模糊的請求（如「我想要 Lo-fi」）提升為精確、可執行的意圖規格，包含維度目標和禁止項。

**核心概念**：將需求從「我想要 Lo-fi」提升為可執行的意圖維度，可用於精確的聲音導航和生成。

**主要功能：**
- 自然語言解析以提取聲音維度
- 參考音訊分析（您想要的）
- 反參考音訊分析（您不想要的）
- 具有精確值的維度目標生成
- 禁止項識別（禁止的維度範圍）
- 衝突檢測和解決

**目的：**
此 playbook 是聲音探索的入口點。使用者以自然語言描述其聲音需求，playbook 建立結構化的意圖卡，可供 `sonic_navigation` 使用以尋找匹配的聲音。

**相關 Playbooks：**
- `sonic_navigation` - 使用意圖卡搜尋聲音
- `sonic_prospecting_lite` - 使用意圖卡進行聲音生成
- `sonic_decision_trace` - 追蹤意圖卡迭代

詳細規格請參考：`playbooks/specs/sonic_intent_card.json`

## 輸入參數

### 必填輸入

- **intent_description** (`string`)
  - Natural language description (e.g., 'I want something more airy and warm')

### 選填輸入

- **reference_audio** (`file`)
  - Reference audio file

- **anti_reference_audio** (`file`)
  - Anti-reference (sounds you don't want)

- **target_scene** (`enum`)
  - Options: meditation, brand_audio, ui_sound, background_music, sfx, ambience

## 輸出結果

**Artifacts:**

- `sonic_intent_card`
  - Schema defined in spec file

## 執行步驟

### Step 1: Parse Natural Language Intent

Extract sonic dimensions from natural language

- **Action**: `nlp_parse`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: extracted_dimensions, extracted_prohibitions

### Step 2: Analyze Reference Audio

Extract fingerprint from reference audio

- **Action**: `analyze_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.reference_audio exists
- **Outputs**: reference_fingerprint

### Step 3: Analyze Anti-Reference

Extract fingerprint from anti-reference

- **Action**: `analyze_audio`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.anti_reference_audio exists
- **Outputs**: anti_fingerprint

### Step 4: Generate Dimension Targets

Map parsed intent to dimension values

- **Action**: `map_to_dimensions`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Identify Prohibitions

Define forbidden dimension ranges

- **Action**: `extract_prohibitions`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Create Intent Card

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **dimension_conflict**
  - Rule: Detect conflicting dimension requirements
  - Action: `warn_and_ask_clarification`

- **unrealistic_target**
  - Rule: Flag impossible dimension combinations
  - Action: `suggest_alternatives`

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **自然語言聲音請求**
   - 將「我想要更空靈和溫暖的東西」轉換為維度目標
   - 提取溫暖和亮度維度
   - 產生精確的意圖卡

2. **基於參考的意圖**
   - 使用參考音訊定義所需的聲音特性
   - 從參考中提取指紋
   - 建立符合參考風格的意圖卡

3. **反參考意圖**
   - 使用反參考音訊指定要避免的聲音
   - 提取禁止的維度範圍
   - 建立包含排除項的意圖卡

4. **場景特定意圖**
   - 為特定使用場景（冥想、品牌音訊等）建立意圖
   - 為場景設定適當的維度目標
   - 確保意圖符合場景需求

## 使用範例

### 範例 1：僅文字意圖

```json
{
  "intent_description": "我想要更空靈和溫暖的東西，有寬敞的感覺",
  "target_scene": "meditation"
}
```

**預期輸出：**
- `sonic_intent_card` artifact，包含：
  - 維度目標：溫暖（高）、亮度（高）、空間感（高）
  - 目標場景：冥想
  - 無禁止項

### 範例 2：參考音訊意圖

```json
{
  "intent_description": "類似這個但稍微溫暖一點",
  "reference_audio": "/path/to/reference.wav",
  "target_scene": "background_music"
}
```

**預期輸出：**
- `sonic_intent_card` artifact，包含：
  - 提取的參考指紋
  - 基於參考 +「更溫暖」調整的維度目標
  - 目標場景：背景音樂

### 範例 3：反參考意圖

```json
{
  "intent_description": "溫暖的環境音，但不要太暗",
  "reference_audio": "/path/to/reference.wav",
  "anti_reference_audio": "/path/to/anti_reference.wav",
  "target_scene": "ambience"
}
```

**預期輸出：**
- `sonic_intent_card` artifact，包含：
  - 參考指紋（溫暖環境音）
  - 反參考指紋（太暗）
  - 禁止項：亮度 < 閾值
  - 目標場景：環境音

## 技術細節

**聲音維度：**
- **溫暖**：溫暖/冷調軸（感知）
- **亮度**：明亮/暗調軸（感知）
- **空間感**：寬敞/親密軸（感知）
- 基於本體論的其他維度

**維度提取：**
- 解析自然語言中的維度關鍵字
- 將關鍵字映射到維度值（0-100 刻度）
- 處理相對術語（「更多」、「更少」、「稍微」）

**參考音訊分析：**
- 使用 `sonic_fingerprint_extractor` 提取音訊指紋
- 將指紋映射到維度空間
- 根據文字意圖調整維度

**反參考分析：**
- 提取反參考指紋
- 識別禁止的維度範圍
- 建立排除規則

**衝突檢測：**
- 檢測衝突的維度需求
- 標記不可能的組合
- 建議替代方案

**意圖卡結構：**
`sonic_intent_card` artifact 包含：
- 維度目標（溫暖、亮度、空間感等）
- 維度禁止項（禁止的範圍）
- 目標場景（冥想、品牌音訊等）
- 參考指紋（如提供）
- 反參考指紋（如提供）

**工具依賴：**
- `sonic_intent_parser` - 解析自然語言意圖
- `sonic_audio_analyzer` - 分析參考/反參考音訊
- `sonic_fingerprint_extractor` - 提取音訊指紋

**責任分配：**
- AI Auto：40%（自動解析和分析）
- AI Propose：50%（維度映射建議）
- Human Only：10%（複雜意圖的最終審核）

## 相關 Playbooks

- **sonic_navigation** - 使用意圖卡搜尋聲音
- **sonic_prospecting_lite** - 使用意圖卡進行聲音生成
- **sonic_decision_trace** - 追蹤意圖卡迭代
- **sonic_quick_calibration** - 校準感知軸以進行意圖映射

## 參考資料

- **規格文件**: `playbooks/specs/sonic_intent_card.json`
