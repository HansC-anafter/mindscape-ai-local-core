---
playbook_code: sonic_asset_sourcing
version: 1.0.0
locale: zh-TW
name: "Asset Sourcing & Licensing Pipeline"
description: "Establish stable commercial asset sources (self-recorded/purchased/CC0)"
kind: user_workflow
capability_code: sonic_space
---

# Asset Sourcing & Licensing Pipeline

Establish stable commercial asset sources (self-recorded/purchased/CC0)

## 概述

資產來源與授權流程 playbook 為 Sonic Space 系統建立穩定的商業資產來源。它處理來自各種來源的音訊資產註冊和驗證，包括自行錄製內容、購買授權、CC0/公共領域材料和合作協議。

**主要功能：**
- 支援多種來源類型（自行製作、授權購買、CC0/公共領域、合作夥伴）
- 自動授權文件解析和驗證
- 基於來源類型和授權條款的風險等級評估
- 使用範圍和限制追蹤
- 建立來源記錄以供資產溯源

**目的：**
此 playbook 是 Sonic Space 系統中風險緩解的基礎。它確保所有音訊資產在進入系統前都有適當的來源文件和風險評估。這是保護免受法律問題並確保合規性的關鍵預處理步驟。

**相關 Playbooks：**
- `sonic_asset_import` - 在建立來源後匯入資產
- `sonic_license_governance` - 註冊詳細授權資訊
- `sonic_export_gate` - 使用來源記錄進行匯出合規檢查

詳細規格請參考：`playbooks/specs/sonic_asset_sourcing.json`

## 輸入參數

### 必填輸入

- **source_type** (`enum`)
  - Asset source type
  - Options: self_produced, licensed_purchase, cc0_public_domain, partnership

### 選填輸入

- **source_url** (`string`)
  - Source URL or receipt link

- **license_document** (`file`)
  - License document or receipt

- **purchase_date** (`date`)
  - Purchase or acquisition date

- **provider_name** (`string`)
  - Provider or platform name (e.g., Artlist, Epidemic Sound)

- **target_count** (`integer`)
  - Target number of assets to acquire
  - Default: `1`

## 輸出結果

**Artifacts:**

- `asset_source`
  - Schema defined in spec file

## 執行步驟

### Step 1: Validate Source Type

Verify source type is valid and supported

- **Action**: `validate`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Collect Source Information

Gather source URL, receipt, license document, etc.

- **Action**: `collect_metadata`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 3: Verify License

Parse and verify license document

- **Action**: `verify_license`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.license_document exists

### Step 4: Assess Risk Level

Evaluate risk level based on source type and license

- **Action**: `risk_assessment`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: risk_level, risk_factors

### Step 5: Create Source Record

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **unknown_source_block**
  - Rule: Unknown source type must be manually reviewed
  - Action: `require_human_approval`

- **high_risk_alert**
  - Rule: High/Critical risk sources require explicit approval
  - Action: `require_human_approval`

- **license_verification**
  - Rule: Commercial use requires verified license document
  - Action: `reject_if_unverified`

## 所需能力

This playbook requires the following capabilities:

- `sonic_space`

**Note**: Capabilities are specified using `capability_code`, not hardcoded tools or APIs.

## 資料邊界

- **Local Only**: False
- **Cloud Allowed**: True

**Note**: Data locality is defined in the playbook spec and takes precedence over manifest defaults.

## 使用場景

1. **自行製作資產註冊**
   - 註冊自行錄製或自行創作的音訊資產
   - 記錄建立日期和所有權
   - 標記為內部使用的低風險

2. **授權購買註冊**
   - 註冊從素材庫購買的資產（Artlist、Epidemic Sound 等）
   - 解析購買收據和授權文件
   - 提取使用條款和限制

3. **CC0/公共領域註冊**
   - 註冊 Creative Commons Zero 或公共領域資產
   - 驗證公共領域狀態
   - 記錄署名要求（如有）

4. **合作夥伴資產註冊**
   - 註冊來自合作協議的資產
   - 記錄合作條款
   - 追蹤使用限制和義務

## 使用範例

### 範例 1：註冊購買的資產

```json
{
  "source_type": "licensed_purchase",
  "provider_name": "Artlist",
  "source_url": "https://artlist.io/receipt/xxx",
  "license_document": "/path/to/license.pdf",
  "purchase_date": "2026-01-01",
  "target_count": 50
}
```

**預期輸出：**
- `asset_source` artifact，包含：
  - 來源類型：licensed_purchase
  - 提供者：Artlist
  - 風險等級：低（購買資產通常為低風險）
  - 從授權文件提取的使用範圍
  - 已建立的來源記錄

### 範例 2：註冊自行製作的資產

```json
{
  "source_type": "self_produced",
  "purchase_date": "2026-01-01",
  "target_count": 1
}
```

**預期輸出：**
- `asset_source` artifact，包含：
  - 來源類型：self_produced
  - 風險等級：低
  - 完整使用權限（商業、廣播、串流等）
  - 無限制

## 技術細節

**來源類型：**
- `self_produced`：自行錄製或自行創作的資產（最低風險）
- `licensed_purchase`：從素材庫購買的資產（低風險，有使用限制）
- `cc0_public_domain`：CC0 或公共領域資產（低風險，可能需要署名）
- `partnership`：來自合作協議的資產（風險可變，取決於條款）

**風險評估：**
- **低**：自行製作、適當授權的購買、驗證的 CC0
- **中**：條款不明確的合作資產、有限授權範圍
- **高**：授權不明確、缺少文件、過期授權
- **嚴重**：潛在版權問題、未驗證來源

**授權驗證：**
- 解析授權文件（PDF、文字等）
- 提取使用範圍（商業、廣播、串流、衍生、重新分發）
- 識別限制（地區、平台、時長限制）
- 驗證授權到期日

**來源記錄結構：**
`asset_source` artifact 包含：
- 來源類型和提供者資訊
- 授權文件路徑和驗證狀態
- 風險等級和風險因素
- 允許的使用範圍
- 限制（地區、平台、時長）
- 購買/取得日期
- 建立元數據

**責任分配：**
- AI Auto：10%（自動驗證和解析）
- AI Propose：30%（風險評估建議）
- Human Only：60%（最終批准，特別是對高風險來源）

**工具依賴：**
- 授權文件解析器
- 風險評估引擎

**效能：**
- 預估時間：每個來源約 30 秒
- 支援批次註冊
- 大型批次的異步處理

## 相關 Playbooks

- **sonic_asset_import** - 在建立來源後匯入資產
- **sonic_license_governance** - 註冊詳細授權資訊
- **sonic_export_gate** - 使用來源記錄進行匯出合規檢查
- **sonic_kit_packaging** - 為 kits 匯總來源資訊

## 參考資料

- **規格文件**: `playbooks/specs/sonic_asset_sourcing.json`
- **API 端點**: `POST /api/v1/sonic-space/sources`
