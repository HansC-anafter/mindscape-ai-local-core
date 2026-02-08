---
playbook_code: sonic_delivery
version: 1.0.0
locale: zh-TW
name: "Delivery & License Shipping"
description: "B2B contract/packaging/certificates"
kind: user_workflow
capability_code: sonic_space
---

# Delivery & License Shipping

B2B contract/packaging/certificates

## 概述

交付與授權運送 playbook 處理聲音資產的 B2B 交付，包括合約準備、打包和證書生成。它確保聲音套件和資產向商業客戶的專業交付。

**主要功能：**
- 準備 B2B 合約
- 為交付打包資產
- 生成交付證書
- 處理授權文件

**目的：**
此 playbook 實現聲音資產的專業 B2B 交付，確保在資產交付給客戶前滿足所有法律、授權和文件要求。

**相關 Playbooks：**
- `sonic_kit_packaging` - 在交付前打包資產
- `sonic_license_governance` - 在交付前驗證授權
- `sonic_export_gate` - 最終合規檢查

詳細規格請參考：`playbooks/specs/sonic_delivery.json`

## 輸入參數


## 輸出結果

See spec file for detailed output schema.

## 執行步驟

### Step 1: Prepare Delivery

Prepare B2B contract and packaging

- **Action**: `prepare_delivery`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Generate Certificates

Generate delivery certificates

- **Action**: `generate_certificates`
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

1. **B2B 資產交付**
   - 為資產交付準備合約
   - 專業打包資產
   - 生成交付文件

2. **授權運送**
   - 包含授權文件
   - 生成授權證書
   - 確保法律合規

3. **專業打包**
   - 建立專業交付套件
   - 包含所有必需文件
   - 確保客戶就緒的交付

## 使用範例

### 範例 1：準備交付

```json
{
  "kit_id": "kit_123",
  "client_info": {...},
  "delivery_method": "digital_download",
  "include_certificates": true
}
```

**預期輸出：**
- 帶合約的打包資產
- 交付證書
- 授權文件
- 專業交付套件

## 技術細節

**交付準備：**
- 準備 B2B 合約
- 為交付打包資產
- 生成證書
- 包含所有文件

**工具依賴：**
- 交付和打包系統

## 相關 Playbooks

- **sonic_kit_packaging** - 在交付前打包資產
- **sonic_license_governance** - 在交付前驗證授權
- **sonic_export_gate** - 最終合規檢查

## 參考資料

- **規格文件**: `playbooks/specs/sonic_delivery.json`
