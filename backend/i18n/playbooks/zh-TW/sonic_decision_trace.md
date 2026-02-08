---
playbook_code: sonic_decision_trace
version: 1.0.0
locale: zh-TW
name: "A/B Listening Experiment & Path Recording"
description: "Record decision paths (like Git log)"
kind: user_workflow
capability_code: sonic_space
---

# A/B Listening Experiment & Path Recording

Record decision paths (like Git log)

## 概述

A/B 聆聽實驗與路徑記錄 playbook 記錄聲音選擇和導航過程中的決策路徑，類似於 Git log。它追蹤使用者選擇、A/B 比較和決策歷史，以啟用回溯和從過往決策中學習。

**主要功能：**
- 記錄 A/B 聆聽決策
- 建立決策追蹤路徑（類似 Git log）
- 追蹤導航歷史
- 啟用回溯到先前的決策
- 從決策模式中學習

**目的：**
此 playbook 讓使用者能夠追蹤其聲音選擇歷程並從過往決策中學習。對於需要探索多個選項並重新造訪先前選擇的迭代聲音設計工作流程至關重要。

**相關 Playbooks：**
- `sonic_navigation` - 記錄導航決策
- `sonic_intent_card` - 追蹤意圖卡迭代
- `sonic_bookmark` - 將書籤連結到決策追蹤

詳細規格請參考：`playbooks/specs/sonic_decision_trace.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Record Decision

Record A/B listening decision

- **Action**: `record_decision`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Create Trace

Create decision trace path (like Git log)

- **Action**: `create_trace`
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

1. **A/B 比較追蹤**
   - 記錄聲音選項之間的選擇
   - 追蹤選擇了哪些聲音及原因
   - 建立決策歷史以供分析

2. **迭代設計工作流程**
   - 追蹤聲音選擇的多個迭代
   - 啟用回溯到先前選擇
   - 從決策模式中學習

3. **決策分析**
   - 分析隨時間變化的決策模式
   - 識別偏好的聲音特性
   - 改善未來的聲音選擇

## 使用範例

### 範例 1：記錄 A/B 決策

```json
{
  "intent_card_id": "intent_123",
  "option_a_id": "segment_001",
  "option_b_id": "segment_002",
  "selected_option": "segment_001",
  "decision_reason": "More spacious feel"
}
```

**預期輸出：**
- `decision_trace` artifact，包含：
  - 決策記錄（時間戳記、選項、選擇）
  - 連結到意圖卡
  - 決策原因

## 技術細節

**決策記錄：**
- 記錄 A/B 比較選擇
- 將決策連結到意圖卡
- 儲存決策原因和上下文
- 建立可追蹤的決策路徑

**追蹤結構：**
- 類似 Git log 結構
- 線性或分支決策路徑
- 每個決策的時間戳記和上下文
- 連結到相關 artifacts（意圖卡、段）

**工具依賴：**
- 決策追蹤系統

## 相關 Playbooks

- **sonic_navigation** - 記錄導航決策
- **sonic_intent_card** - 追蹤意圖卡迭代
- **sonic_bookmark** - 將書籤連結到決策追蹤

## 參考資料

- **規格文件**: `playbooks/specs/sonic_decision_trace.json`
