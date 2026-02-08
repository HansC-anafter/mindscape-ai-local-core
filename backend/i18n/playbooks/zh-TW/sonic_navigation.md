---
playbook_code: sonic_navigation
version: 1.1.0
locale: zh-TW
name: "Sonic Navigation"
description: "Three-stage search: Query Vector → Recall → Feature Rerank + License Filter"
kind: user_workflow
capability_code: sonic_space
---

# Sonic Navigation

Three-stage search: Query Vector → Recall → Feature Rerank + License Filter

## 概述

Sonic Navigation 是 Sonic Space 系統中的核心搜尋與探索 playbook。它實作三階段搜尋流程，結合向量相似度搜尋與基於特徵的重新排序和授權合規過濾。

**核心概念**：向量搜尋找到「相似」的聲音，但特徵維度過濾掉「相似但錯誤」的聲音。這種兩階段方法確保語義相似性和精確的維度匹配。

**三階段流程：**
1. **階段 1：查詢向量建構** - 使用選定的策略將意圖卡轉換為查詢向量
2. **階段 2：向量搜尋召回** - 使用向量相似度搜尋召回 3 倍候選項
3. **階段 3：特徵重新排序 + 授權過濾** - 按維度匹配分數重新排序，並按授權合規性過濾

**主要功能：**
- 多種查詢策略（基於文字、音訊參考、書籤）
- 雙空間架構（搜尋空間 + 控制空間）
- 基於目標場景的授權合規過濾
- A/B 比較準備以支援決策
- 快速回應時間（< 5 秒 P95）

**目的：**
此 playbook 讓使用者能夠找到符合其聲音意圖的音訊資產，同時確保法律合規性。這是探索聲音潛在空間的主要介面。

**相關 Playbooks：**
- `sonic_intent_card` - 在導航前建立意圖卡
- `sonic_embedding_build` - 為搜尋建立 embedding 索引
- `sonic_decision_trace` - 記錄導航決策
- `sonic_bookmark` - 將導航結果儲存為書籤

詳細規格請參考：`playbooks/specs/sonic_navigation.json`

## 輸入參數

### 必填輸入

- **intent_card_id** (`string`)
  - Sonic Intent Card ID

- **embedding_index_id** (`string`)
  - Embedding Index ID

### 選填輸入

- **top_k** (`integer`)
  - Number of candidates to return (final)
  - Default: `10`

- **recall_multiplier** (`integer`)
  - Recall 3x candidates for rerank
  - Default: `3`

- **diversity_factor** (`float`)
  - Diversity factor (0-1)
  - Default: `0.3`

- **query_strategy** (`enum`)
  - Query vector construction strategy
  - Default: `text`
  - Options: text, audio_reference, bookmark

- **reference_audio_id** (`string`)
  - Reference audio ID for strategy B

- **anti_reference_audio_id** (`string`)
  - Anti-reference audio ID for strategy B

- **bookmark_id** (`string`)
  - Bookmark ID for strategy C

## 輸出結果

**Artifacts:**

- `candidate_set`
  - Schema defined in spec file

## 執行步驟

### Step 1: Load Intent Card

Load the sonic intent card with dimension_targets and target_scene

- **Action**: `load_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Construct Query Vector (Stage 1)

Convert intent to query vector using selected strategy

- **Action**: `intent_to_vector`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Vector Search Recall (Stage 2)

Recall 3x candidates for reranking

- **Action**: `similarity_search`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 4: Feature Rerank (Stage 3a)

Rerank candidates by dimension_targets match score

- **Action**: `rerank_by_features`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: License Filter (Stage 3b)

Filter by target_scene → required_usage_scope mapping

- **Action**: `filter_by_license_compliance`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 6: Generate Candidate Set

Create the final candidate set artifact

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 7: Prepare A/B Options

Present one dimension decision at a time

- **Action**: `prepare_comparison`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **license_compliance**
  - Rule: Only return assets with valid licenses for target_scene usage
  - Action: `filter_out`

- **high_risk_block**
  - Rule: Block high/critical risk assets from candidates
  - Action: `filter_out`

- **empty_result**
  - Rule: Handle zero results gracefully
  - Action: `suggest_relaxed_criteria`

- **response_time**
  - Rule: Search must complete in < 5 seconds
  - Action: `timeout_with_partial_results`

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **基於文字的聲音搜尋**
   - 使用自然語言描述搜尋聲音
   - 範例：「尋找溫暖、寬敞的冥想環境音」
   - 使用基於文字的查詢策略

2. **參考音訊搜尋**
   - 尋找與參考音訊檔案相似的聲音
   - 可指定反參考（要避免的聲音）
   - 使用音訊參考查詢策略

3. **基於書籤的導航**
   - 從儲存的書籤位置導航
   - 探索潛在空間中附近的聲音
   - 使用基於書籤的查詢策略

4. **場景特定搜尋**
   - 按使用場景過濾結果（冥想、品牌音訊、UI 聲音等）
   - 確保目標場景的授權合規性
   - 僅返回可商業使用的資產

## 使用範例

### 範例 1：基於文字的搜尋

```json
{
  "intent_card_id": "intent_123",
  "embedding_index_id": "index_456",
  "query_strategy": "text",
  "top_k": 10,
  "recall_multiplier": 3,
  "diversity_factor": 0.3
}
```

**預期輸出：**
- `candidate_set` artifact，包含 10 個排序的候選項
- 所有候選項都有目標場景的有效授權
- 準備好 A/B 比較選項

### 範例 2：音訊參考搜尋

```json
{
  "intent_card_id": "intent_123",
  "embedding_index_id": "index_456",
  "query_strategy": "audio_reference",
  "reference_audio_id": "audio_789",
  "anti_reference_audio_id": "audio_101",
  "top_k": 5
}
```

**預期輸出：**
- `candidate_set` artifact，包含與參考相似的聲音
- 排除與反參考相似的聲音
- 僅授權合規的結果

### 範例 3：書籤導航

```json
{
  "intent_card_id": "intent_123",
  "embedding_index_id": "index_456",
  "query_strategy": "bookmark",
  "bookmark_id": "bookmark_456",
  "top_k": 15,
  "diversity_factor": 0.5
}
```

**預期輸出：**
- `candidate_set` artifact，從書籤位置探索
- 潛在空間中的多樣化結果
- 準備好 A/B 比較

## 技術細節

**查詢策略：**
- `text`：使用文字 embedding 將意圖描述轉換為查詢向量
- `audio_reference`：使用參考音訊 embedding 作為查詢向量
- `bookmark`：使用書籤位置作為查詢向量

**搜尋流程：**
1. 載入包含維度目標和目標場景的意圖卡
2. 使用選定的策略建構查詢向量
3. 向量搜尋：召回 `top_k * recall_multiplier` 個候選項
4. 特徵重新排序：按維度匹配評分候選項
5. 授權過濾：按目標場景 → 使用範圍映射過濾
6. 產生包含前 K 個結果的候選集
7. 準備 A/B 比較選項

**效能目標：**
- 回應時間：< 5 秒（P95）
- 命中率：> 70%（候選項符合意圖）
- 授權合規性：100%（所有結果都可商業使用）

**雙空間架構：**
- **搜尋空間**：向量相似度（找到語義相似的聲音）
- **控制空間**：特徵維度（按精確需求過濾）

**授權過濾：**
- 將目標場景映射到所需的使用範圍
- 過濾掉沒有有效授權的資產
- 阻擋高/嚴重風險資產

**候選集結構：**
`candidate_set` artifact 包含：
- 候選段列表及其分數
- 每個候選項的維度匹配分數
- 授權合規狀態
- 準備好的 A/B 比較配對

## 相關 Playbooks

- **sonic_intent_card** - 在導航前建立意圖卡
- **sonic_embedding_build** - 為搜尋建立 embedding 索引
- **sonic_decision_trace** - 記錄導航決策
- **sonic_bookmark** - 將導航結果儲存為書籤
- **sonic_segment_extract** - 為 embedding 提取段

## 參考資料

- **規格文件**: `playbooks/specs/sonic_navigation.json`
- **API 端點**: `POST /api/v1/sonic-space/navigation/search`
