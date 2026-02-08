---
playbook_code: sonic_latent_map
version: 1.0.0
locale: zh-TW
name: "Sonic Clustering & Map Generation"
description: "Generate Latent Map / Mood Map"
kind: user_workflow
capability_code: sonic_space
---

# Sonic Clustering & Map Generation

Generate Latent Map / Mood Map

## 概述

聲音聚類與地圖生成 playbook 通過聚類音訊 embeddings 生成潛在地圖和情緒地圖。它建立聲音潛在空間的可視化表示，以供探索和導航。

**主要功能：**
- 聚類音訊 embeddings
- 生成潛在空間地圖
- 建立情緒地圖
- 可視化聲音空間結構

**目的：**
此 playbook 讓使用者能夠通過聚類和地圖生成可視化和理解聲音潛在空間的結構。地圖幫助使用者更有效地導航和探索聲音空間。

**相關 Playbooks：**
- `sonic_embedding_build` - 為地圖建立 embeddings
- `sonic_navigation` - 使用地圖進行導航
- `sonic_latent_prospecting` - 探索已映射的區域

詳細規格請參考：`playbooks/specs/sonic_latent_map.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Load Embeddings

Load audio embeddings

- **Action**: `load_embeddings`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 2: Cluster Embeddings

Cluster embeddings for latent map

- **Action**: `cluster_embeddings`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Generate Map

Generate Latent Map / Mood Map

- **Action**: `generate_map`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

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

1. **潛在空間可視化**
   - 生成潛在空間結構地圖
   - 可視化聲音分佈
   - 理解聲音空間組織

2. **情緒地圖建立**
   - 建立基於情緒的聲音地圖
   - 按情緒特性組織聲音
   - 支援基於情緒的導航

3. **探索輔助**
   - 使用地圖引導探索
   - 識別有趣的區域
   - 規劃導航路徑

## 使用範例

### 範例 1：生成潛在地圖

```json
{
  "embedding_index_id": "index_123",
  "map_type": "latent",
  "clustering_method": "kmeans"
}
```

**預期輸出：**
- 帶聚類的潛在空間地圖
- 聲音空間的可視化表示
- 所有聲音的聚類分配

## 技術細節

**地圖生成：**
- 從索引載入 embeddings
- 使用選定的方法聚類 embeddings
- 生成地圖可視化
- 建立聚類分配

**地圖類型：**
- `latent`：潛在空間結構地圖
- `mood`：基於情緒的組織地圖

**工具依賴：**
- `sonic_vector_search` - 載入 embeddings
- 聚類演算法

## 相關 Playbooks

- **sonic_embedding_build** - 為地圖建立 embeddings
- **sonic_navigation** - 使用地圖進行導航
- **sonic_latent_prospecting** - 探索已映射的區域

## 參考資料

- **規格文件**: `playbooks/specs/sonic_latent_map.json`
