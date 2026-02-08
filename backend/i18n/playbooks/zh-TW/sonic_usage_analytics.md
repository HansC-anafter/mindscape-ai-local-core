---
playbook_code: sonic_usage_analytics
version: 1.0.0
locale: zh-TW
name: "Usage Tracking & Effectiveness Analysis"
description: "Material → Scene → Effectiveness correlation (Audio BI)"
kind: user_workflow
capability_code: sonic_space
---

# Usage Tracking & Effectiveness Analysis

Material → Scene → Effectiveness correlation (Audio BI)

## 概述

使用追蹤與效果分析 playbook 追蹤和分析音訊資產在系統中的使用方式。它提供資產受歡迎程度、使用模式和使用者行為的洞察。

**主要功能：**
- 追蹤資產使用
- 分析使用模式
- 生成使用報告
- 提供使用洞察

**目的：**
此 playbook 讓使用者能夠了解音訊資產的使用方式，識別受歡迎的資產，並獲得使用模式洞察，以改善資產管理和策劃。

**相關 Playbooks：**
- `sonic_navigation` - 追蹤導航使用
- `sonic_decision_trace` - 分析決策模式
- `sonic_dataset_curation` - 使用分析進行策劃

詳細規格請參考：`playbooks/specs/sonic_usage_analytics.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Collect Usage Data

Collect material → scene → effectiveness data

- **Action**: `collect_usage_data`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Analyze Correlation

Analyze Audio BI correlations

- **Action**: `analyze_correlation`
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

1. **使用追蹤**
   - 追蹤哪些資產使用最多
   - 識別受歡迎的聲音
   - 監控使用模式

2. **分析報告**
   - 生成使用報告
   - 分析使用趨勢
   - 為策劃提供洞察

3. **資產管理**
   - 使用分析進行資產優先排序
   - 識別未充分利用的資產
   - 優化資產庫

## 使用範例

### 範例 1：生成使用報告

```json
{
  "time_range": "last_30_days",
  "report_type": "asset_popularity"
}
```

**預期輸出：**
- 使用分析報告
- 資產受歡迎程度排名
- 使用模式洞察

## 技術細節

**分析追蹤：**
- 追蹤系統中的資產使用
- 記錄使用事件
- 分析使用模式
- 生成洞察

**工具依賴：**
- 分析和報告系統

## 相關 Playbooks

- **sonic_navigation** - 追蹤導航使用
- **sonic_decision_trace** - 分析決策模式
- **sonic_dataset_curation** - 使用分析進行策劃

## 參考資料

- **規格文件**: `playbooks/specs/sonic_usage_analytics.json`
