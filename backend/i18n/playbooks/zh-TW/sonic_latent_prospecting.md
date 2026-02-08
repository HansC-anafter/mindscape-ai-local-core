---
playbook_code: sonic_latent_prospecting
version: 1.0.0
locale: zh-TW
name: "Latent Space Sparse Region Exploration"
description: "Explore new sounds in low-density regions, form new bookmarks"
kind: user_workflow
capability_code: sonic_space
---

# Latent Space Sparse Region Exploration

Explore new sounds in low-density regions, form new bookmarks

## 概述

潛在空間稀疏區域探索 playbook 探索潛在空間中低密度區域的新聲音，啟用發現獨特和未探索的聲音特性。它從這些探索中建立新書籤。

**主要功能：**
- 識別潛在空間中的稀疏（低密度）區域
- 在未探索區域探索新聲音
- 從發現中建立書籤
- 擴展聲音庫覆蓋範圍

**目的：**
此 playbook 讓使用者能夠通過探索潛在空間的未充分利用區域來發現新的獨特聲音。這是 `sonic_prospecting_lite` 的進階版本，專注於稀疏區域探索。

**相關 Playbooks：**
- `sonic_prospecting_lite` - 基本探索（P0 版本）
- `sonic_bookmark` - 從探索建立書籤
- `sonic_navigation` - 導航到稀疏區域
- `sonic_quick_calibration` - 為探索校準軸

詳細規格請參考：`playbooks/specs/sonic_latent_prospecting.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Identify Sparse Regions

Identify low-density regions in latent space

- **Action**: `identify_sparse_regions`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 2: Explore Region

Explore new sounds in sparse regions

- **Action**: `explore_region`
- **Tool**: `sonic_space.sonic_axes_steer`
  - ✅ Format: `capability.tool_name`

### Step 3: Create Bookmark

Form new bookmarks from exploration

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

1. **稀疏區域發現**
   - 識別潛在空間中的未探索區域
   - 發現獨特聲音特性
   - 擴展聲音庫多樣性

2. **新穎聲音生成**
   - 在低密度區域生成聲音
   - 建立獨特聲音變化
   - 探索創意可能性

3. **庫擴展**
   - 填補聲音庫覆蓋範圍的空白
   - 添加多樣化聲音特性
   - 改善搜尋結果多樣性

## 使用範例

### 範例 1：探索稀疏區域

```json
{
  "region_type": "sparse",
  "exploration_strategy": "density_based"
}
```

**預期輸出：**
- 在稀疏區域發現的新聲音
- 為有趣發現建立的書籤
- 擴展的聲音庫覆蓋範圍

## 技術細節

**稀疏區域識別：**
- 分析潛在空間中的 embedding 密度
- 識別低密度區域
- 映射未探索區域

**探索流程：**
1. 使用密度分析識別稀疏區域
2. 使用軸導航探索區域
3. 生成或發現新聲音
4. 為有趣發現建立書籤

**工具依賴：**
- `sonic_vector_search` - 分析潛在空間密度
- `sonic_axes_steer` - 導航和探索區域

## 相關 Playbooks

- **sonic_prospecting_lite** - 基本探索（P0 版本）
- **sonic_bookmark** - 從探索建立書籤
- **sonic_navigation** - 導航到稀疏區域
- **sonic_quick_calibration** - 為探索校準軸

## 參考資料

- **規格文件**: `playbooks/specs/sonic_latent_prospecting.json`
