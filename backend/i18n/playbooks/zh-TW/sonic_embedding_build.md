---
playbook_code: sonic_embedding_build
version: 1.0.0
locale: zh-TW
name: "Embedding Build"
description: "Audio → Vector vectorization"
kind: user_workflow
capability_code: sonic_space
---

# Embedding Build

Audio → Vector vectorization

## 概述

Embedding Build playbook 將音訊段轉換為向量 embeddings，以啟用潛在空間中的語義搜尋。這是基於向量的聲音導航和探索的基礎。

**主要功能：**
- 支援多種 embedding 模型（CLAP、AudioCLIP、Wav2Vec2）
- 批次 embedding 生成
- 向量索引以實現快速相似度搜尋
- Embedding 統計和品質指標

**目的：**
此 playbook 建立為 `sonic_navigation` 中的向量搜尋提供動力的 embedding 索引。沒有 embeddings，語義搜尋是不可能的。

**相關 Playbooks：**
- `sonic_segment_extract` - 在 embedding 前提取段
- `sonic_navigation` - 使用 embeddings 進行向量搜尋
- `sonic_quick_calibration` - 使用 embeddings 校準感知軸

詳細規格請參考：`playbooks/specs/sonic_embedding_build.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Load Segments

Load audio segments for embedding

- **Action**: `load_segments`
- **Tool**: `sonic_space.sonic_audio_analyzer`
  - ✅ Format: `capability.tool_name`

### Step 2: Generate Embeddings

Generate audio embeddings using CLAP/AudioCLIP

- **Action**: `generate_embeddings`
- **Tool**: `sonic_space.sonic_embedding_generator`
  - ✅ Format: `capability.tool_name`

### Step 3: Index Embeddings

Index embeddings for vector search

- **Action**: `index_embeddings`
- **Tool**: `sonic_space.sonic_vector_search`
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

1. **初始索引建立**
   - 為新的音訊集合建立 embedding 索引
   - 批次處理所有段
   - 建立可搜尋的向量資料庫

2. **增量更新**
   - 將新段添加到現有索引
   - 更新已修改段的 embeddings
   - 維護索引一致性

3. **模型比較**
   - 使用不同模型產生 embeddings
   - 比較搜尋品質
   - 為使用案例選擇最佳模型

## 使用範例

### 範例 1：建立 CLAP Embeddings

```json
{
  "segment_ids": ["seg_001", "seg_002", "seg_003", ...],
  "embedding_model": "clap"
}
```

**預期輸出：**
- Embedding 向量（CLAP 為 512 維）
- 在向量資料庫中建立索引
- 準備好進行相似度搜尋

## 技術細節

**Embedding 模型：**
- **CLAP**：512 維，文字-音訊聯合 embedding
- **AudioCLIP**：1024 維，音訊-視覺-文字 embedding
- **Wav2Vec2**：768 維，自監督音訊表示

**處理流程：**
1. 載入音訊段
2. 使用選定的模型產生 embeddings
3. 在向量資料庫中建立索引（pgvector）
4. 產生索引統計

**向量索引：**
- 儲存在 PostgreSQL 中，使用 pgvector 擴充
- 使用餘弦相似度進行搜尋
- IVFFlat 或 HNSW 索引以提升效能
- 支援批次插入

**工具依賴：**
- `sonic_audio_analyzer` - 載入段
- `sonic_embedding_generator` - 產生 embeddings
- `sonic_vector_search` - 建立索引

**效能：**
- CLAP：每個段約 0.1 秒
- AudioCLIP：每個段約 0.2 秒
- Wav2Vec2：每個段約 0.15 秒
- 建議對大型集合進行批次處理

## 相關 Playbooks

- **sonic_segment_extract** - 在 embedding 前提取段
- **sonic_navigation** - 使用 embeddings 進行向量搜尋
- **sonic_quick_calibration** - 使用 embeddings 校準感知軸
- **sonic_prospecting_lite** - 使用 embeddings 探索潛在空間

## 參考資料

- **規格文件**: `playbooks/specs/sonic_embedding_build.json`
