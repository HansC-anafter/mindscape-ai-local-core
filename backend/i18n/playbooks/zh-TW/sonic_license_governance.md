---
playbook_code: sonic_license_governance
version: 1.0.0
locale: zh-TW
name: "License & Provenance Governance"
description: "Register source, assess risk, and generate license cards"
kind: user_workflow
capability_code: sonic_space
---

# License & Provenance Governance

Register source, assess risk, and generate license cards

## 概述

授權與來源治理 playbook 對於管理音訊資產的法律合規性和風險評估至關重要。它註冊音訊資產的來源，評估法律和合規風險，並產生管理資產使用方式的授權卡。

**主要功能：**
- 來源類型分類（自有、CC 授權、購買、客戶提供、AI 生成）
- 自動授權文件解析和條款提取
- 風險等級評估（低、中、高、嚴重）
- 使用規則生成（允許/禁止的使用場景）
- 建立包含完整來源資訊的授權卡

**目的：**
此 playbook 確保所有音訊資產在商業環境中使用前都有適當的授權文件和風險評估。這是資產匯入流程中的關鍵步驟，可防止法律問題。

**相關 Playbooks：**
- `sonic_asset_import` - 在註冊授權前匯入資產
- `sonic_export_gate` - 使用授權卡進行匯出合規檢查
- `sonic_kit_packaging` - 為 sound kit 分發匯總授權

詳細規格請參考：`playbooks/specs/sonic_license_governance.json`

## 輸入參數

### 必填輸入

- **audio_asset_id** (`string`)
  - Audio asset ID

- **source_type** (`enum`)
  - Asset source type
  - Options: self_owned, cc_licensed, purchased, client_provided, ai_generated

### 選填輸入

- **license_document** (`file`)
  - License document file

- **usage_scope** (`object`)

- **attribution_required** (`boolean`)
  - Default: `False`

- **attribution_text** (`string`)

- **expiry_date** (`date`)

## 輸出結果

**Artifacts:**

- `license_card`
  - Schema defined in spec file

## 執行步驟

### Step 1: Classify Source Type

Categorize the audio source

- **Action**: `classify`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 2: Extract License Information

Parse license document for terms

- **Action**: `parse_license_document`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Condition**: input.license_document exists

### Step 3: Assess Risk Level

Evaluate legal and compliance risk

- **Action**: `risk_assessment`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool
- **Outputs**: risk_level, risk_factors

### Step 4: Generate Usage Rules

Create allowed/prohibited usage rules

- **Action**: `generate_rules`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

### Step 5: Create License Card

- **Action**: `create_artifact`
- **Tool**: `core_llm.generate`
  - ⚠️ Note: Using core tool

## 安全檢查

- **unknown_source_block**
  - Rule: Unknown source type must be manually reviewed
  - Action: `require_human_approval`

- **high_risk_alert**
  - Rule: High/Critical risk assets require explicit approval
  - Action: `require_human_approval`

- **commercial_use_check**
  - Rule: Commercial use requires verified license
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

1. **商業資產註冊**
   - 註冊從素材庫（Artlist、Epidemic Sound）購買的音訊資產
   - 解析授權文件並提取使用條款
   - 評估商業使用的風險等級

2. **CC 授權資產管理**
   - 註冊 Creative Commons 授權的資產
   - 提取署名要求
   - 設定使用範圍限制

3. **客戶提供資產治理**
   - 註冊客戶提供的資產
   - 評估客戶提供內容的風險
   - 根據客戶協議產生使用規則

4. **自有資產文件化**
   - 記錄自行錄製或自行創作的資產
   - 標記為內部使用的低風險
   - 設定適當的使用範圍

5. **AI 生成資產合規**
   - 註冊 AI 生成的音訊資產
   - 評估是否符合 AI 生成政策
   - 如需要，設定使用限制

## 使用範例

### 範例 1：註冊購買的資產

```json
{
  "audio_asset_id": "asset_123",
  "source_type": "purchased",
  "license_document": "/path/to/license.pdf",
  "usage_scope": {
    "commercial": true,
    "broadcast": true,
    "streaming": true,
    "derivative": false,
    "redistribution": false
  },
  "expiry_date": "2026-12-31"
}
```

**預期輸出：**
- `license_card` artifact，包含解析的授權條款
- 風險等級評估（購買資產通常為低風險）
- 基於授權文件的使用規則

### 範例 2：註冊 CC 授權資產

```json
{
  "audio_asset_id": "asset_456",
  "source_type": "cc_licensed",
  "attribution_required": true,
  "attribution_text": "Music by Artist Name, CC BY 4.0",
  "usage_scope": {
    "commercial": true,
    "derivative": true,
    "redistribution": true
  }
}
```

**預期輸出：**
- `license_card` artifact，包含 CC 授權資訊
- 記錄署名要求
- 允許商業使用（需署名）的使用規則

### 範例 3：註冊自有資產

```json
{
  "audio_asset_id": "asset_789",
  "source_type": "self_owned",
  "usage_scope": {
    "commercial": true,
    "broadcast": true,
    "streaming": true,
    "derivative": true,
    "redistribution": true
  }
}
```

**預期輸出：**
- `license_card` artifact，標記為自有
- 低風險等級評估
- 完整使用權限文件化

## 技術細節

**風險評估等級：**
- **低**：自有、適當授權的購買資產
- **中**：有限制的 CC 授權、有文件的客戶提供
- **高**：授權不明確、授權過期、缺少文件
- **嚴重**：潛在版權侵權、未驗證來源

**來源類型分類：**
- `self_owned`：自行錄製或自行創作的資產
- `cc_licensed`：Creative Commons 授權的資產
- `purchased`：從素材庫或市場購買的資產
- `client_provided`：客戶提供的資產
- `ai_generated`：AI 生成的音訊資產

**使用範圍欄位：**
- `commercial`：允許商業使用
- `broadcast`：允許廣播使用
- `streaming`：允許串流使用
- `derivative`：允許衍生作品
- `redistribution`：允許重新分發

**授權卡結構：**
`license_card` artifact 包含：
- 資產 ID 和來源類型
- 風險等級和風險因素
- 使用範圍（允許/禁止的場景）
- 署名要求
- 授權到期日
- 授權文件參考

**責任分配：**
- AI Auto：30%（自動分類和解析）
- AI Propose：40%（風險評估建議）
- Human Only：30%（高風險資產的最終審核）

## 相關 Playbooks

- **sonic_asset_import** - 在註冊授權前匯入資產
- **sonic_export_gate** - 使用授權卡進行匯出合規檢查
- **sonic_kit_packaging** - 為 sound kit 分發匯總授權
- **sonic_navigation** - 在搜尋結果中按授權合規性過濾資產

## 參考資料

- **規格文件**: `playbooks/specs/sonic_license_governance.json`
