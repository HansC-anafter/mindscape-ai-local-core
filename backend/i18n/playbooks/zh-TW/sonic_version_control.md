---
playbook_code: sonic_version_control
version: 1.0.0
locale: zh-TW
name: "Asset Version Control & Rollback"
description: "Audio Git / Asset Registry"
kind: user_workflow
capability_code: sonic_space
---

# Asset Version Control & Rollback

Audio Git / Asset Registry

## 概述

資產版本控制與回滾 playbook 為音訊資產提供版本控制，類似於程式碼的 Git。它追蹤變更、建立版本快照，並啟用回滾到先前版本。

**主要功能：**
- 建立版本快照
- 追蹤變更（Audio Git）
- 在資產註冊表中註冊資產
- 啟用回滾到先前版本

**目的：**
此 playbook 為音訊資產啟用版本控制，讓使用者能夠追蹤變更、維護歷史記錄，並在需要時回滾到先前版本。對於迭代聲音設計工作流程至關重要。

**相關 Playbooks：**
- `sonic_decision_trace` - 追蹤決策歷史
- `sonic_asset_import` - 匯入資產以供版本控制
- `sonic_dsp_transform` - 將變形追蹤為版本

詳細規格請參考：`playbooks/specs/sonic_version_control.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Create Version

Create new version snapshot

- **Action**: `create_version`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Track Changes

Track changes (Audio Git)

- **Action**: `track_changes`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Register Asset

Register in Asset Registry

- **Action**: `register_asset`
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

1. **版本追蹤**
   - 追蹤音訊資產的變更
   - 建立版本快照
   - 維護資產歷史

2. **回滾能力**
   - 回滾到先前版本
   - 從不想要的變更中恢復
   - 維護版本歷史

3. **資產註冊表**
   - 在中央註冊表中註冊資產
   - 追蹤資產版本
   - 啟用資產發現

## 使用範例

### 範例 1：建立版本

```json
{
  "asset_id": "asset_123",
  "version_description": "Added reverb processing",
  "create_snapshot": true
}
```

**預期輸出：**
- 已建立新版本快照
- 在版本歷史中追蹤變更
- 在資產註冊表中註冊資產

## 技術細節

**版本控制：**
- 建立版本快照
- 追蹤變更（類似 Git）
- 維護版本歷史
- 啟用回滾

**資產註冊表：**
- 所有資產的中央註冊表
- 版本追蹤
- 資產發現和管理

**工具依賴：**
- 版本控制系統
- 資產註冊表

## 相關 Playbooks

- **sonic_decision_trace** - 追蹤決策歷史
- **sonic_asset_import** - 匯入資產以供版本控制
- **sonic_dsp_transform** - 將變形追蹤為版本

## 參考資料

- **規格文件**: `playbooks/specs/sonic_version_control.json`
