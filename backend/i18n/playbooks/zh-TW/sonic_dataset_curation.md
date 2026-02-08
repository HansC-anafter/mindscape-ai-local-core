---
playbook_code: sonic_dataset_curation
version: 1.0.0
locale: zh-TW
name: "Dataset Curation"
description: "Curate Theme/Brand/Project dataset packages"
kind: user_workflow
capability_code: sonic_space
---

# Dataset Curation

Curate Theme/Brand/Project dataset packages

## 概述

資料集策劃 playbook 通過選擇和組織音訊資產為主題/品牌/專案資料集套件進行策劃。它讓使用者能夠為特定主題、品牌或專案建立專業化的聲音庫。

**主要功能：**
- 使用向量搜尋選擇資產
- 將資產組織成主題集合
- 為特定使用案例建立資料集套件
- 支援主題/品牌/專案分類

**目的：**
此 playbook 讓使用者能夠為特定主題、品牌或專案建立策劃的聲音庫。它對於建立符合特定美學或功能需求的專業化集合很有用。

**相關 Playbooks：**
- `sonic_navigation` - 尋找要包含在資料集中的資產
- `sonic_kit_packaging` - 為分發打包策劃的資料集
- `sonic_license_governance` - 確保所有資產都有有效授權

詳細規格請參考：`playbooks/specs/sonic_dataset_curation.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Select Assets

Select assets for dataset

- **Action**: `select_assets`
- **Tool**: `sonic_space.sonic_vector_search`
  - ✅ Format: `capability.tool_name`

### Step 2: Curate Dataset

Curate Theme/Brand/Project dataset package

- **Action**: `curate_dataset`
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

1. **主題式策劃**
   - 為特定主題建立集合（自然、城市、奇幻）
   - 按美學或情緒組織聲音
   - 建立主題聲音庫

2. **品牌特定集合**
   - 策劃符合品牌識別的聲音
   - 建立品牌特定聲音庫
   - 維護品牌一致性

3. **專案資料集**
   - 為特定專案組織聲音
   - 建立專案特定聲音庫
   - 支援專案工作流程

## 使用範例

### 範例 1：主題資料集

```json
{
  "dataset_name": "Nature Ambience Collection",
  "dataset_type": "theme",
  "theme": "nature",
  "selection_criteria": {
    "dimensions": {
      "warmth": [60, 80],
      "spatiality": [70, 90]
    }
  }
}
```

**預期輸出：**
- 策劃的資料集，包含自然主題聲音
- 按選擇標準組織
- 準備好進行打包或分發

## 技術細節

**策劃流程：**
1. 使用向量搜尋選擇資產
2. 按選擇標準過濾（維度、主題等）
3. 組織成資料集結構
4. 建立資料集套件

**資料集類型：**
- `theme`：主題集合（自然、城市等）
- `brand`：品牌特定集合
- `project`：專案特定集合

**工具依賴：**
- `sonic_vector_search` - 尋找要策劃的資產

## 相關 Playbooks

- **sonic_navigation** - 尋找要包含在資料集中的資產
- **sonic_kit_packaging** - 為分發打包策劃的資料集
- **sonic_license_governance** - 確保所有資產都有有效授權

## 參考資料

- **規格文件**: `playbooks/specs/sonic_dataset_curation.json`
