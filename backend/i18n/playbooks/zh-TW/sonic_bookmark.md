---
playbook_code: sonic_bookmark
version: 1.0.0
locale: zh-TW
name: "Vector Bookmark & Reuse"
description: "Create reusable sonic coordinate bookmarks"
kind: user_workflow
capability_code: sonic_space
---

# Vector Bookmark & Reuse

Create reusable sonic coordinate bookmarks

## 概述

向量書籤與重用 playbook 建立可重用的聲音座標書籤，讓使用者能夠儲存和重新造訪潛在空間中的特定位置。書籤作為導航、插值和聲音生成的參考點。

**主要功能：**
- 從參考音訊或 embeddings 建立書籤
- 在潛在空間中儲存書籤座標
- 重用書籤進行導航和探索
- 將書籤連結到代表性段

**目的：**
此 playbook 讓使用者能夠儲存有趣的聲音位置以供後續使用。書籤對於 `sonic_prospecting_lite`（插值/外推）和 `sonic_navigation`（基於書籤的搜尋）至關重要。

**相關 Playbooks：**
- `sonic_navigation` - 使用書籤進行導航
- `sonic_prospecting_lite` - 使用書籤進行插值/外推
- `sonic_decision_trace` - 追蹤書籤建立決策

詳細規格請參考：`playbooks/specs/sonic_bookmark.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Load Reference

Load reference audio or embedding

- **Action**: `load_reference`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 2: Create Bookmark

Create reusable sonic coordinate bookmark

- **Action**: `create_bookmark`
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

1. **儲存有趣的聲音**
   - 儲存在導航期間發現的聲音
   - 為未來探索建立參考點
   - 建立個人聲音庫

2. **插值點**
   - 為聲音間插值建立書籤
   - 定義聲音生成的起點和終點
   - 探索中間位置

3. **外推基礎**
   - 建立書籤作為外推的起點
   - 從已知位置探索維度極端
   - 沿軸產生變化

## 使用範例

### 範例 1：從音訊建立書籤

```json
{
  "reference_audio_id": "audio_123",
  "bookmark_name": "Warm Ambient Reference"
}
```

**預期輸出：**
- `sonic_bookmark` artifact，包含：
  - 書籤 ID 和名稱
  - 潛在空間中的 embedding 座標
  - 連結到參考音訊段

## 技術細節

**書籤建立：**
- 從參考音訊提取 embedding
- 在潛在空間中儲存座標
- 連結到代表性段
- 建立可重用的參考點

**書籤使用：**
- 在 `sonic_navigation` 中用於基於書籤的搜尋
- 在 `sonic_prospecting_lite` 中用於插值/外推
- 從儲存的位置啟用探索

**工具依賴：**
- `sonic_vector_search` - 載入參考並提取座標

## 相關 Playbooks

- **sonic_navigation** - 使用書籤進行導航
- **sonic_prospecting_lite** - 使用書籤進行插值/外推
- **sonic_decision_trace** - 追蹤書籤建立決策

## 參考資料

- **規格文件**: `playbooks/specs/sonic_bookmark.json`
